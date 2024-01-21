import openai
from fastapi import FastAPI, Form, Depends, Request
from decouple import config
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models import Conversation, SessionLocal
from utils import send_message, logger

import requests
import speech_recognition as sr

# import soundfile as sf
from pydub import AudioSegment
import os  # Added for checking file existence
os.environ["PATH"] += os.pathsep + r'C:\FFmpeg\bin'

def convert_opus_to_wav(opus_file):
    try:
        audio = AudioSegment.from_file(opus_file)
        wav_file = "audio_message.wav"
        audio.export(wav_file, format="wav")
        print(f"WAV file created: {os.path.exists(wav_file)}")
        return wav_file
    except Exception as e:
        logger.error(f"Error converting Opus to WAV: {e}")
        return None

app = FastAPI()
# Set up the OpenAI API client
openai.api_key = config("OPENAI_API_KEY")

# Dependency
def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

@app.get("/")
async def index():
    return {"msg": "working"}

@app.post("/message")
async def reply(request: Request, Body: str = Form(default=None), MediaUrl0: str = Form(default=None), db: Session = Depends(get_db)):
    form_data = await request.form()
    whatsapp_number = form_data['From'].split("whatsapp:")[-1]
    print(f"Sending the ChatGPT response to this number: {whatsapp_number}")

    if MediaUrl0:  # If there's an audio message
        opus_file = download_audio(MediaUrl0)  # Download the audio file from Twilio
        print(f"Opus file downloaded: {os.path.exists(opus_file)}")  # Check if the Opus file was downloaded
        wav_file = convert_opus_to_wav(opus_file)  # Convert the Opus file to WAV
        if wav_file is None:
            logger.error("Failed to convert Opus to WAV")
            return ""
        Body = speech_to_text(wav_file)  # Convert the audio to text
        if Body is None:
            logger.error("Failed to convert speech to text")
            return ""

    # Call the OpenAI API to generate text with ChatGPT
    messages = [{"role": "user", "content": Body}]
    messages.append({"role": "system", "content": "The text below was sent from a teenager (Gen Alpha to Gen Z age) and was recieved by a parent who doesn't understand the meaning. Your job is to translate the text with proper grammar and in a way so that it's understandable to boomers. Only send back the translated version without extra words such as translation:."})
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages,
        max_tokens=200,
        n=1,
        stop=None,
        temperature=0.5
        )

    # The generated text
    chatgpt_response = response.choices[0].message.content

    # Store the conversation in the database
    try:
        conversation = Conversation(
            sender=whatsapp_number,
            message=Body,
            response=chatgpt_response
            )
        db.add(conversation)
        db.commit()
        logger.info(f"Conversation #{conversation.id} stored in database")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error storing conversation in database: {e}")
    send_message(whatsapp_number, chatgpt_response)
    return ""

def download_audio(url):
    try:
        response = requests.get(url)
        filename = "audio_message.opus"
        with open(filename, 'wb') as audio:
            audio.write(response.content)
        return filename
    except Exception as e:
        logger.error(f"Error downloading audio: {e}")
        return None

def speech_to_text(audio_file):
    try:
        r = sr.Recognizer()
        with sr.AudioFile(audio_file) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data)
        return text
    except Exception as e:
        logger.error(f"Error converting speech to text: {e}")
        return None