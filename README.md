# Audio Silence Cutter API

A Flask web service that processes audio files by removing silence gaps, designed for deployment on Render.

## Features

- Accepts various audio formats (MP3, WAV, FLAC, M4A, AAC, OGG)
- Removes silence from audio files using configurable parameters
- Returns processed audio files
- RESTful API suitable for integration with automation tools like n8n

## Configuration Parameters

- **min_silence_len**: 100ms (minimum length of silence to be detected)
- **silence_thresh**: -30dB (threshold below which audio is considered silence)
- **keep_silence**: 25ms (amount of silence to keep around non-silent parts)

## API Endpoints

### POST /process-audio

Processes an audio file by removing silence gaps.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Parameters:
  - `audio` (file): The audio file to process
  - `output_format` (optional string): Output format (mp3, wav, etc. - defaults to mp3)

**Response:**
- Success: Returns the processed audio file
- Error: JSON error message with appropriate HTTP status code

**Example using curl:**
```bash
curl -X POST \
  -F "audio=@your_audio_file.mp3" \
  -F "output_format=mp3" \
  https://your-render-app.onrender.com/process-audio \
  --output processed_audio.mp3
```

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

1. **Method**: POST
2. **URL**: `https://your-render-app.onrender.com/process-audio`
3. **Body**: Form-Data
   - Key: `audio`, Type: File, Value: Your audio file
   - Key: `output_format`, Type: Text, Value: `mp3` (optional)
4. **Response**: Binary Data

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