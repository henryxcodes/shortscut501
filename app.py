from flask import Flask, request, jsonify, Response
from pydub import AudioSegment
from pydub.silence import detect_nonsilent, split_on_silence
import os
import tempfile
import logging
from datetime import datetime
import threading
import uuid
import zipfile
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('silence_cutter.log')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Job storage (same pattern as Claude API)
jobs = {}

# File size limit in bytes (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

def cut_silence(audio_path, min_silence_len=100, silence_thresh=-30, keep_silence=30):
    logger.info(f"Processing audio file: {audio_path}")
    logger.info(f"Parameters: min_silence_len={min_silence_len}ms, silence_thresh={silence_thresh}dB, keep_silence={keep_silence}ms")
    
    # Load the audio file
    try:
        audio = AudioSegment.from_file(audio_path)
        logger.info(f"Audio loaded successfully. Duration: {len(audio)/1000:.2f} seconds")
    except Exception as e:
        logger.error(f"Error loading audio file: {str(e)}")
        raise
    
    # Split audio on silence, keeping short silences as padding
    try:
        chunks = split_on_silence(
            audio,
            min_silence_len=min_silence_len,
            silence_thresh=silence_thresh,
            keep_silence=keep_silence
        )
        if not chunks:
            logger.warning("No audio chunks found after splitting on silence, returning original audio.")
            return audio
            
        logger.info(f"Found {len(chunks)} chunks after splitting on silence.")
    except Exception as e:
        logger.error(f"Error splitting audio on silence: {str(e)}")
        raise
    
    # Combine all chunks
    try:
        result = AudioSegment.empty()
        for chunk in chunks:
            result += chunk
        logger.info(f"Processed audio duration: {len(result)/1000:.2f} seconds")
        return result
    except Exception as e:
        logger.error(f"Error combining audio chunks: {str(e)}")
        raise

def export_mp3_with_size_limit(audio, output_path, max_size_bytes=MAX_FILE_SIZE):
    """Export audio as MP3 with automatic compression to stay under size limit"""
    logger.info(f"Exporting audio to MP3 format with max size: {max_size_bytes/1024/1024:.1f}MB")
    
    # Start with high quality and reduce if needed
    bitrates = [256, 192, 160, 128, 96, 64, 32]  # kbps
    
    for bitrate in bitrates:
        temp_path = output_path + f"_temp_{bitrate}.mp3"
        try:
            # Export with current bitrate
            audio.export(
                temp_path, 
                format="mp3", 
                bitrate=f"{bitrate}k",
                parameters=["-q:a", "2"]  # Good quality
            )
            
            # Check file size
            file_size = os.path.getsize(temp_path)
            logger.info(f"Bitrate {bitrate}kbps produced file size: {file_size/1024/1024:.2f}MB")
            
            if file_size <= max_size_bytes:
                # File is within size limit, rename to final output
                os.rename(temp_path, output_path)
                logger.info(f"Successfully exported MP3 at {bitrate}kbps bitrate, size: {file_size/1024/1024:.2f}MB")
                return output_path
            else:
                # File too large, try next lower bitrate
                os.unlink(temp_path)
                
        except Exception as e:
            logger.error(f"Error exporting at {bitrate}kbps: {str(e)}")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            continue
    
    # If we get here, even the lowest bitrate was too large
    # Try one more time with extreme compression
    try:
        audio.export(
            output_path, 
            format="mp3", 
            bitrate="24k",
            parameters=["-q:a", "9"]  # Lowest quality but smallest size
        )
        file_size = os.path.getsize(output_path)
        logger.warning(f"Used extreme compression (24kbps) - final size: {file_size/1024/1024:.2f}MB")
        return output_path
    except Exception as e:
        logger.error(f"Failed to export even with extreme compression: {str(e)}")
        raise Exception("Unable to compress audio under 50MB limit")

def process_audio_background(job_id, input_path, output_path):
    """Background processing function"""
    try:
        jobs[job_id]['status'] = 'processing'
        logger.info(f"[{job_id}] Starting background processing")
        
        # Process the audio (same as before)
        processed_audio = cut_silence(input_path)
        
        # Export as MP3 with size limit instead of WAV
        output_path = output_path.replace('.wav', '.mp3')  # Change extension to MP3
        export_mp3_with_size_limit(processed_audio, output_path)
        logger.info(f"[{job_id}] Exported processed audio to: {output_path}")
        
        # Update job status
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['output_path'] = output_path
        jobs[job_id]['completed_at'] = datetime.now()
        logger.info(f"[{job_id}] Processing completed successfully")
        
    except Exception as e:
        logger.error(f"[{job_id}] Error in background processing: {str(e)}")
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)
        jobs[job_id]['completed_at'] = datetime.now()
        
        # Clean up on error
        if os.path.exists(input_path):
            os.unlink(input_path)
        if os.path.exists(output_path):
            os.unlink(output_path)

def process_single_file(file, request_id, file_index=""):
    """Process a single audio file and return the result info"""
    result = {
        'filename': file.filename,
        'success': False,
        'error': None,
        'output_path': None,
        'file_size': 0
    }
    
    file_log_id = f"{request_id}{file_index}"
    logger.info(f"[{file_log_id}] Processing file: {file.filename}")
    
    input_path = None
    output_path = None
    
    try:
        # Create temporary files for input and output
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as input_temp:
            file.save(input_temp.name)
            input_path = input_temp.name
        logger.info(f"[{file_log_id}] Saved input file to: {input_path}")
        
        # Output will be WAV to maintain quality
        output_path = input_path.replace('.wav', '_processed.wav')
        
        # Process the audio
        processed_audio = cut_silence(input_path)
        
        # Export as WAV (high quality)
        processed_audio.export(output_path, format="wav")
        logger.info(f"[{file_log_id}] Exported processed audio to: {output_path}")
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"[{file_log_id}] Successfully processed WAV file, size: {file_size/1024/1024:.2f}MB")
            
            result['success'] = True
            result['output_path'] = output_path
            result['file_size'] = file_size
        else:
            result['error'] = 'Processed file not found'
            logger.error(f"[{file_log_id}] Processed file not found")
    
    except Exception as e:
        error_msg = str(e)
        result['error'] = error_msg
        logger.error(f"[{file_log_id}] Error processing audio: {error_msg}")
        
        # Clean up on error
        if output_path and os.path.exists(output_path):
            os.unlink(output_path)
    
    finally:
        # Always clean up input file
        if input_path and os.path.exists(input_path):
            os.unlink(input_path)
    
    return result

@app.route('/process-audio', methods=['POST'])
def process_audio():
    request_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    logger.info(f"[{request_id}] Received new request")
    
    # Check if we have any files
    if not request.files:
        logger.error(f"[{request_id}] No files provided in request")
        return jsonify({'error': 'No files provided'}), 400
    
    # Get all files (handles both single 'file' and multiple files)
    files = []
    if 'file' in request.files:
        # Single file case (backward compatibility)
        files = [request.files['file']]
    else:
        # Multiple files case - get all files from request
        for key in request.files:
            file_list = request.files.getlist(key)
            files.extend(file_list)
    
    # Filter out empty filenames
    files = [f for f in files if f.filename != '']
    
    if not files:
        logger.error(f"[{request_id}] No valid files selected")
        return jsonify({'error': 'No valid files selected'}), 400
    
    logger.info(f"[{request_id}] Processing {len(files)} file(s)")
    
    # Process all files
    results = []
    successful_files = []
    
    for i, file in enumerate(files):
        file_index = f"_{i+1}" if len(files) > 1 else ""
        result = process_single_file(file, request_id, file_index)
        results.append(result)
        
        if result['success']:
            successful_files.append(result)
    
    # Handle results
    if not successful_files:
        logger.error(f"[{request_id}] No files processed successfully")
        error_summary = {
            'error': 'No files processed successfully',
            'details': [{'filename': r['filename'], 'error': r['error']} for r in results if not r['success']]
        }
        return jsonify(error_summary), 500
    
    # Single file - return directly (backward compatibility)
    if len(files) == 1 and successful_files:
        result = successful_files[0]
        logger.info(f"[{request_id}] Returning single WAV file")
        
        with open(result['output_path'], 'rb') as f:
            audio_data = f.read()
        
        # Clean up
        os.unlink(result['output_path'])
        
        return Response(
            audio_data,
            mimetype='audio/wav',
            headers={
                'Content-Disposition': f'attachment; filename={result["filename"].rsplit(".", 1)[0]}_processed.wav'
            }
        )
    
    # Multiple files - create zip archive
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as zip_temp:
            zip_path = zip_temp.name
        
        logger.info(f"[{request_id}] Creating zip archive with {len(successful_files)} processed files")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add processed files to zip
            for result in successful_files:
                if result['success'] and os.path.exists(result['output_path']):
                    processed_filename = f"{result['filename'].rsplit('.', 1)[0]}_processed.wav"
                    zipf.write(result['output_path'], processed_filename)
                    logger.info(f"[{request_id}] Added {processed_filename} to zip")
            
            # Add processing summary
            summary = {
                'total_files': len(files),
                'successful_files': len(successful_files),
                'failed_files': len(files) - len(successful_files),
                'processing_summary': [
                    {
                        'filename': r['filename'],
                        'success': r['success'],
                        'error': r['error'],
                        'file_size_mb': round(r['file_size'] / (1024*1024), 2) if r['success'] else 0
                    } for r in results
                ]
            }
            zipf.writestr('processing_summary.json', json.dumps(summary, indent=2))
        
        # Read zip file
        with open(zip_path, 'rb') as f:
            zip_data = f.read()
        
        # Clean up all temporary files
        for result in successful_files:
            if os.path.exists(result['output_path']):
                os.unlink(result['output_path'])
        os.unlink(zip_path)
        
        logger.info(f"[{request_id}] Returning zip archive with {len(successful_files)} processed files")
        
        return Response(
            zip_data,
            mimetype='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename=processed_audio_{request_id}.zip'
            }
        )
    
    except Exception as e:
        logger.error(f"[{request_id}] Error creating zip archive: {str(e)}")
        # Clean up on error
        for result in successful_files:
            if os.path.exists(result['output_path']):
                os.unlink(result['output_path'])
        return jsonify({'error': f'Error creating zip archive: {str(e)}'}), 500

@app.route('/job/<job_id>', methods=['GET'])
def get_job_status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    
    if job['status'] == 'completed':
        # Return the processed audio file
        output_path = job['output_path']
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"Returning MP3 file, size: {file_size/1024/1024:.2f}MB")
            
            with open(output_path, 'rb') as f:
                audio_data = f.read()
            
            # Clean up files after sending
            os.unlink(job['input_path'])
            os.unlink(output_path)
            del jobs[job_id]  # Clean up job
            
            return audio_data, 200, {
                'Content-Type': 'audio/mpeg',  # Changed to MP3 content type
                'Content-Disposition': 'attachment; filename=processed_audio.mp3'  # Changed filename extension
            }
        else:
            return jsonify({'error': 'Processed file not found'}), 500
            
    elif job['status'] == 'failed':
        error_msg = job.get('error', 'Unknown error')
        # Clean up on failure
        if os.path.exists(job['input_path']):
            os.unlink(job['input_path'])
        del jobs[job_id]
        return jsonify({'error': error_msg}), 500
    else:
        # Still processing
        return jsonify({
            'job_id': job_id,
            'status': job['status'],
            'filename': job['filename'],
            'created_at': job['created_at'].isoformat(),
            'message': 'Audio processing in progress...'
        }), 200

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'active_jobs': len([j for j in jobs.values() if j['status'] in ['pending', 'processing']])
    })

@app.route('/', methods=['GET'])
def home():
    """
    Health check endpoint
    """
    return jsonify({
        'status': 'running',
        'service': 'Audio Silence Cutter',
        'parameters': {
            'min_silence_len': 50,
            'silence_thresh': -40,
            'keep_silence': 33
        }
    })

if __name__ == '__main__':
    logger.info("Starting Silence Cutter API server...")
    # Create upload folder if it doesn't exist
    os.makedirs('temp_uploads', exist_ok=True)
    
    # Run the app
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True) 
