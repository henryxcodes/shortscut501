from flask import Flask, request, jsonify, send_file
from pydub import AudioSegment
from pydub.silence import split_on_silence
import tempfile
import os
import io
from werkzeug.utils import secure_filename
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
UPLOAD_FOLDER = 'temp_uploads'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'flac', 'm4a', 'aac', 'ogg'}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Silence cutting parameters
MIN_SILENCE_LEN = 45  # minimum length of silence in milliseconds
SILENCE_THRESH = -45  # threshold in dB below which audio is considered silence
KEEP_SILENCE = 30     # amount of silence to keep around non-silent parts in milliseconds

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_audio(audio_file_path, output_format='mp3'):
    """
    Process audio file by cutting silence using the specified parameters
    """
    try:
        # Load audio file
        audio = AudioSegment.from_file(audio_file_path)
        logger.info(f"Loaded audio file: duration={len(audio)}ms")
        
        # Split audio on silence
        chunks = split_on_silence(
            audio,
            min_silence_len=MIN_SILENCE_LEN,
            silence_thresh=SILENCE_THRESH,
            keep_silence=KEEP_SILENCE
        )
        
        logger.info(f"Split audio into {len(chunks)} chunks")
        
        if not chunks:
            logger.warning("No audio chunks found, returning original audio")
            return audio
        
        # Combine chunks back together (removes silence between them)
        processed_audio = AudioSegment.empty()
        for chunk in chunks:
            processed_audio += chunk
        
        logger.info(f"Processed audio: original={len(audio)}ms, processed={len(processed_audio)}ms")
        
        return processed_audio
        
    except Exception as e:
        logger.error(f"Error processing audio: {str(e)}")
        raise

@app.route('/', methods=['GET'])
def home():
    """
    Health check endpoint
    """
    return jsonify({
        'status': 'running',
        'service': 'Audio Silence Cutter',
        'parameters': {
            'min_silence_len': MIN_SILENCE_LEN,
            'silence_thresh': SILENCE_THRESH,
            'keep_silence': KEEP_SILENCE
        }
    })

@app.route('/process-audio', methods=['POST'])
def process_audio_endpoint():
    """
    Main endpoint for processing audio files
    Accepts: multipart/form-data with 'audio' file
    Returns: processed audio file
    """
    try:
        # Check if file was uploaded
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        file = request.files['audio']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': f'File type not allowed. Allowed types: {ALLOWED_EXTENSIONS}'}), 400
        
        # Get output format from request (default to mp3)
        output_format = request.form.get('output_format', 'mp3').lower()
        if output_format not in ALLOWED_EXTENSIONS:
            output_format = 'mp3'
        
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{filename.split(".")[-1]}')
        file.save(temp_input.name)
        
        try:
            # Process the audio
            processed_audio = process_audio(temp_input.name, output_format)
            
            # Create temporary output file
            temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{output_format}')
            processed_audio.export(temp_output.name, format=output_format)
            
            # Generate output filename
            base_name = filename.rsplit('.', 1)[0]
            output_filename = f"{base_name}_processed.{output_format}"
            
            # Return the processed file
            return send_file(
                temp_output.name,
                as_attachment=True,
                download_name=output_filename,
                mimetype=f'audio/{output_format}'
            )
            
        finally:
            # Clean up temporary files
            try:
                os.unlink(temp_input.name)
                if 'temp_output' in locals():
                    os.unlink(temp_output.name)
            except:
                pass
        
    except Exception as e:
        logger.error(f"Error in process_audio_endpoint: {str(e)}")
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for monitoring
    """
    return jsonify({'status': 'healthy'}), 200

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 50MB'}), 413

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Create upload folder if it doesn't exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 