# Audio Silence Cutter API

A Flask web service that processes audio files by removing silence gaps, designed for deployment on Render.

## Features

- Accepts various audio formats (MP3, WAV, FLAC, M4A, AAC, OGG)
- Removes silence from audio files using configurable parameters
- **Single file processing**: Returns processed audio file directly
- **Batch processing**: Handles multiple files at once with robust error handling
- Returns processed audio files (WAV format for single files, ZIP archive for multiple files)
- Includes processing summary with detailed results for each file in batch mode
- RESTful API suitable for integration with automation tools like n8n

## Configuration Parameters

- **min_silence_len**: 100ms (minimum length of silence to be detected)
- **silence_thresh**: -30dB (threshold below which audio is considered silence)
- **keep_silence**: 0ms (no artificial padding - removes all silence buffer)

## API Endpoints

### POST /process-audio

Processes one or more audio files by removing silence gaps.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Parameters:
  - `file` (file): Single audio file to process (for backward compatibility)
  - OR multiple files with any field names for batch processing

**Response:**
- **Single file**: Returns the processed audio file directly (WAV format)
- **Multiple files**: Returns a ZIP archive containing all successfully processed files plus a processing summary JSON
- **Error**: JSON error message with appropriate HTTP status code

**Single file example using curl:**
```bash
curl -X POST \
  -F "file=@your_audio_file.mp3" \
  https://your-render-app.onrender.com/process-audio \
  --output processed_audio.wav
```

**Multiple files example using curl:**
```bash
curl -X POST \
  -F "file1=@audio1.mp3" \
  -F "file2=@audio2.wav" \
  -F "file3=@audio3.flac" \
  https://your-render-app.onrender.com/process-audio \
  --output processed_audio_batch.zip
```

**Batch Processing Features:**
- Processes multiple files concurrently
- Continues processing even if some files fail
- Returns ZIP archive with all successful files
- Includes `processing_summary.json` with detailed results for each file
- Robust error handling - failed files don't affect successful ones

### GET /

Returns service status and configuration parameters.

### GET /health

Health check endpoint for monitoring.

## Deployment on Render

1. Create a new Web Service on Render
2. Connect your GitHub repository containing this code
3. Render will automatically detect the Python environment
4. The service will be built and deployed using the configuration in `render.yaml`

## Usage with n8n

In n8n, you can use the HTTP Request node with the following configuration:

**Single file processing:**
1. **Method**: POST
2. **URL**: `https://your-render-app.onrender.com/process-audio`
3. **Body**: Form-Data
   - Key: `file`, Type: File, Value: Your audio file
4. **Response**: Binary Data (WAV format)

**Multiple file processing:**
1. **Method**: POST
2. **URL**: `https://your-render-app.onrender.com/process-audio`
3. **Body**: Form-Data
   - Key: `file1`, Type: File, Value: Your first audio file
   - Key: `file2`, Type: File, Value: Your second audio file
   - Add more files as needed with different key names
4. **Response**: Binary Data (ZIP archive with processed files and summary)

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

The service will be available at `http://localhost:5000`

## File Size Limits

- Maximum file size: 50MB
- Supported formats: MP3, WAV, FLAC, M4A, AAC, OGG 