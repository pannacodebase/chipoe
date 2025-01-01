import logging
import scrapetube
import requests
from youtube_transcript_api import YouTubeTranscriptApi
from flask import Flask, render_template, request, jsonify

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

# Function to get channel name and ID
def get_channel_name_and_id(query):
    search_results = scrapetube.get_search(query=query, results_type='channel', limit=1)
    search_results_list = list(search_results)  # Convert the generator to a list
    if search_results_list:
        result = search_results_list[0]
        channel_name = result.get('title', {}).get('simpleText', 'No channel name found')
        channel_id = result.get('channelId', 'No channel ID found')
        return channel_name, channel_id
    return None, None

# Function to get videos from channel ID
def get_videos_from_channel(channel_id, limit=10):
    videos = scrapetube.get_channel(channel_id=channel_id, limit=limit)
    return process_video_results(videos)

# Function to get videos by search query
def get_videos_by_query(query, limit=10):
    videos = scrapetube.get_search(query=query, results_type="video", limit=limit)
    return process_video_results(videos)

# Function to process video results
def process_video_results(videos):
    video_list = []
    for video in videos:
        video_id = video.get('videoId', 'No video ID found')
        title = video.get("title", {}).get("runs", [{}])[0].get("text", "No Title")
        thumbnail = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        url = f"https://www.youtube.com/watch?v={video_id}"
        label = video.get('accessibility', {}).get('accessibilityData', {}).get('label', '')
        views = label.split("views")[0].strip() if "views" in label else "Unknown views"
        time_ago = label.split("ago")[1].strip() if "ago" in label else "Unknown time"
        
        video_list.append({
            "title": title,
            "url": url,
            "thumbnail": thumbnail,
            "views": views,
            "time_ago": time_ago,
        })
    return video_list

# Function to get YouTube transcript
def get_youtube_transcript(video_url):
    video_id = video_url.split("v=")[1]
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([entry['text'] for entry in transcript])
    except Exception as e:
        logging.error(f"Error fetching transcript for video {video_id}: {str(e)}")
        return None

# Function to send transcript to Gemini API
def send_to_gemini(transcript, video_title):
    api_key = "AIzaSyA4lVSciggCKVxhBFRYtUiC4xlQbX_ayjE"  # Replace with your Gemini API key
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    prompt_text = f"""
     You are an expert in large language models and advanced scientific research.. You need to help in summarizing and analyzing content. Write as a three paragraph.
    Don’t use any bold, italic, or formatting.
    Reduce to 6 lines. Summarize without missing important points.
    Title: {video_title}
    Please summarize this video for a layman:
    {transcript}
    """
    data = {"contents": [{"parts": [{"text": prompt_text}]}]}
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "No summary")
    except Exception as e:
        logging.error(f"Error with Gemini API: {str(e)}")
        return "Error summarizing transcript"

@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("index.html")

@app.route("/get_videos", methods=["POST"])
def get_videos():
    data = request.json
    search_type = data.get("search_type")
    query = data.get("query")
    if not search_type or not query:
        return jsonify({"error": "Invalid request"}), 400

    try:
        if search_type == "channel":
            channel_name, channel_id = get_channel_name_and_id(query)
            if not channel_id:
                return jsonify({"error": "Channel not found"}), 404
            videos = get_videos_from_channel(channel_id)
        else:
            videos = get_videos_by_query(query)

        video_data = []
        for video in videos:
            transcript = get_youtube_transcript(video['url'])
            summary = send_to_gemini(transcript or "", video['title'])
            video_data.append({**video, "summary": summary})
        return jsonify(video_data)
    except Exception as e:
        logging.error(f"Error processing request: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(debug=True)
