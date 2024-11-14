import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'Charan@2024#'
    SQLALCHEMY_DATABASE_URI = os.environ.get("postgresql://kolisetty_charan:QJUpLPmZn6rabn6mMfabCILD0nQ6PvbU@dpg-csqsnfqj1k6c73c2fb30-a.oregon-postgres.render.com/coachbot_db")
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    ASSISTANT_ID = os.environ.get('ASSISTANT_ID')