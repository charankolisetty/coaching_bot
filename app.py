import os
import time
import logging
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from config import Config
from openai import OpenAI, OpenAIError

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

openai_client = OpenAI(api_key=app.config['OPENAI_API_KEY'])

# Initial page for user input
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form.get("username")
        industry = request.form.get("industry")
        company = request.form.get("company")

        if not username or not industry or not company:
            return jsonify({"error": "All fields are required"}), 400

        # Store session details
        session["username"] = username
        session["industry"] = industry
        session["company"] = company

        # Check for existing thread or create new one
        thread_id = get_or_create_thread(username, industry, company)
        session["thread_id"] = thread_id

        return redirect(url_for("chat"))

    return render_template("index.html")

# Chat endpoint for handling messages
@app.route("/chat", methods=["GET", "POST"])
def chat():
    if request.method == "POST":
        prompt = request.form.get("prompt")
        thread_id = session.get("thread_id")

        if not prompt or not thread_id:
            return jsonify({"error": "Prompt and Thread ID are required"}), 400

        # Run assistant with the prompt and thread ID
        response_text = run_assistant(thread_id, prompt)
        if response_text:
            # Save chat history if needed
            save_chat(session["username"], prompt, response_text)
            return jsonify({"response": response_text})
        else:
            return jsonify({"error": "Failed to get response"}), 500

    return render_template("chat.html")

def get_or_create_thread(username, industry, company):
    # Check if a thread exists for the user with matching criteria
    thread_id = check_existing_thread(username, industry, company)
    if thread_id:
        return thread_id
    else:
        # Create new thread with instructions about industry and company
        thread = openai_client.beta.threads.create(
            assistant_id=app.config["ASSISTANT_ID"],
            instructions=f"User belongs to {industry} industry and is from {company}."
        )
        return thread.id

def run_assistant(thread_id, prompt):
    try:
        # Add user message to thread
        message = openai_client.beta.threads.messages.create(
            thread_id=thread_id, role="user", content=prompt
        )
        
        # Run assistant and wait for completion
        run = openai_client.beta.threads.runs.create(thread_id=thread_id)
        response = wait_for_run_completion(thread_id, run.id)
        return response
    except OpenAIError as e:
        logging.error(f"OpenAI error: {e}")
        return None

def wait_for_run_completion(thread_id, run_id, sleep_interval=5):
    while True:
        try:
            run = openai_client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            if run.completed_at:
                messages = openai_client.beta.threads.messages.list(thread_id=thread_id)
                return messages.data[-1].content[0].text.value  # Get assistant's last message
        except OpenAIError as e:
            logging.error(f"An error occurred while retrieving the run: {e}")
            return None
        time.sleep(sleep_interval)

def save_chat(username, prompt, response):
    # Implement database save logic here for user chat history, if needed.
    pass

def check_existing_thread(username, industry, company):
    # Implement logic to check for existing thread based on user details.
    pass

if __name__ == "__main__":
    app.run(debug=True)
