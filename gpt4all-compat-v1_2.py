#!/usr/bin/env python3
import logging
import re
import json
import threading
import time
import urllib.request
import socket
import socketserver
import http.server

# Configuration
VERSION = "v1.2"
VERSION_SERVER_PORT = 8086
GPT4ALL_BASE_URL = "http://127.0.0.1:4891"
GPT4ALL_CHAT_COMPLETION_ENDPOINT = f"{GPT4ALL_BASE_URL}/v1/chat/completions"
GPT4ALL_MODELS_ENDPOINT = f"{GPT4ALL_BASE_URL}/v1/models"
#OPENAI_BASE_URL = "https://api.openai.com/v1"  # While not used, these are here from the original structure
#OPENAI_CHAT_COMPLETION_ENDPOINT = f"{OPENAI_BASE_URL}/chat/completions"
#OPENAI_MODELS_ENDPOINT = f"{OPENAI_BASE_URL}/models"

PORT = 8085  # Port for the compatibility layer
STREAM_DELAY = 0.1  # Default delay between sending chunks to simulate streaming
DEBUG = True  # Enable debug messages


def strip_xml_tags(text):
    return re.sub(r'<[^>]*>', '', text)

def extract_user_content(messages):
    """Extracts user content from a messages array, handling both string and object content."""
    gpt4all_messages = []
    for message in messages:
        if message.get("role") == "user":
            content = ""
            if isinstance(message.get("content"), list):
               for item in message.get("content"):
                    if isinstance(item, dict) and item.get("type") == "text":
                        if "text" in item:
                            content += item.get("text")
            else:
                content = message.get("content")
            gpt4all_messages.append({"role": "user", "content": content})
        else:
            gpt4all_messages.append(message)
    return gpt4all_messages
    
def create_initial_chunk(first_word, log_debug):
    """Creates the initial chunk of data for the stream, including the role and type."""
    data_str = 'data: {"choices": [{"index": 0, "delta": {"role": "assistant", "content": "' + first_word + '", "type": "text"}}]}\n\n'
    log_debug(f"create_initial_chunk: data={data_str}")
    return data_str

def create_text_chunk(chunk, log_debug):
    """Creates a text chunk for the stream."""
    escaped_chunk = chunk.replace('"', '\\"').replace('\n', '\\n') # Escape double quotes and newlines
    data_str = 'data: {"choices": [{"index": 0, "delta": {"content": "' + escaped_chunk.strip() + '", "type": "text"}}]}\n\n'
    log_debug(f"create_text_chunk: data={data_str}")
    return data_str

def create_stop_chunk(log_debug, include_finish_reason):
    """Creates the final stop chunk for the stream."""
    if include_finish_reason:
       data_str = 'data: {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}}]}\n'
    else:
        data_str = 'data: [DONE]\n'
    log_debug(f"create_stop_chunk: data={data_str}")
    return data_str

    
def create_done_signal():
    """Creates the [DONE] signal for the end of a stream"""
    return "data: [DONE]\n"

def query_gpt4all(messages, model, temperature, top_p, max_tokens, timeout, log_debug):
        """Send the query to GPT4All and get the response."""
        gpt4all_messages = extract_user_content(messages)

        data = {
            "model": model,
            "messages": gpt4all_messages,
            "temperature": temperature,
            "top_p": top_p,
        }
        if max_tokens is not None:
            data["max_tokens"] = max_tokens
        else:
            data["max_tokens"] = 512
        data = json.dumps(data).encode("utf-8")
        CHAT_COMPLETION_ENDPOINT = GPT4ALL_CHAT_COMPLETION_ENDPOINT
        req = urllib.request.Request(
            CHAT_COMPLETION_ENDPOINT,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        log_debug(f"query_gpt4all: sending data to GPT4All: {data}")

        try:
            log_debug(f"query_gpt4all: Querying GPT4All with: {data}")
            full_response = ""
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = response.read().decode("utf-8")
                log_debug(f"query_gpt4all: GPT4All response: {result}")
                result_data = json.loads(result)
                message = result_data.get("choices", [{}])[0].get("message", {})
                if message:
                    response_text = message.get("content", "")
                    full_response = strip_xml_tags(response_text)
                else:
                    full_response = ""
            return full_response
        except urllib.error.URLError as e:
            log_debug(f"URLError querying GPT4All: {e}")
            return f"Error querying GPT4All: {e}"
        except json.JSONDecodeError as e:
            log_debug(f"JSONDecodeError parsing GPT4All response: {e}")
            return f"Error parsing GPT4All response: {e}"
        except Exception as e:
            log_debug(f"General error querying GPT4All: {e}")
            return f"Error querying GPT4All: {e}"
            
def stream_response(self, response, stream_delay, log_debug, include_finish_reason=True):
        """Simulate streaming by sending chunks of the response, preserving whitespace."""
        log_debug(f"stream_response: response={response}, stream_delay={stream_delay}")
        
        remaining_response = response  # Use a variable for the remaining text

        # Send the initial delta with the role and up to the first 20 words
        chunk = ""
        word_count = 0
        
        # Find the first word
        match = re.match(r'\S+', remaining_response)
        first_word = match.group(0) if match else ""
        
        data_str = create_initial_chunk(first_word, log_debug)
        log_debug(f"stream_response: sending initial delta: data={data_str}")
        self.wfile.write(data_str.encode("utf-8"))
        
        remaining_response = remaining_response[len(first_word):] # Remove initial word, preserving whitespace
        
        while remaining_response:  # Continue until all response is processed
            chunk = ""
            word_count = 0
            while remaining_response and word_count < 20:
                match = re.match(r'(\s*\S+)', remaining_response)  # Match whitespace and the next word
                if not match:
                    break # Break out of while loop if no word found
                
                word_with_space = match.group(0)
                chunk += word_with_space
                remaining_response = remaining_response[len(word_with_space):]
                word_count += 1

            if chunk:
                log_debug(f"stream_response: sending chunk={chunk}")
                data_str = create_text_chunk(chunk, log_debug)
                log_debug(f"stream_response: data={data_str}")
                self.wfile.write(data_str.encode("utf-8"))
                time.sleep(stream_delay)

        log_debug(f"stream_response: sending finish_reason")
        # Always send a [DONE] signal after streaming the response.
        data_str = create_done_signal()
        log_debug(f"stream_response: data={data_str}")
        self.wfile.write(data_str.encode("utf-8"))
        

class StreamingHandler(http.server.BaseHTTPRequestHandler):
    def log_debug(self, message):
        if DEBUG:
            print(f"[DEBUG] {message}")

    def do_POST(self):
        self.log_debug(f"do_POST: path={self.path}")
        # Read the request body
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length)
        try:
            request_data = json.loads(post_data)
            self.log_debug(f"do_POST: request_data={request_data}")
            user_query = request_data.get("prompt", "")
            model = request_data.get("model")
            if not model:
                model = "default"
            stream = request_data.get("stream", False)
            temperature = request_data.get("temperature", 1.0)
            top_p = request_data.get("top_p", 1.0)
            max_tokens = request_data.get("max_tokens", None)
            timeout = request_data.get("timeout", 300)
            messages = request_data.get("messages")
            if not messages:
                messages = [{"role": "user", "content": user_query}]
        except Exception as e:
            self.log_debug(f"Error parsing request: {e}")
            self.send_error(400, str(e))
            return

        if self.path.startswith("/v1/chat/completions") or self.path == "/chat/completions" or self.path.startswith("/streaming/chat/completions") or self.path.startswith("/v1/streaming/chat/completions"):
            # Handle /v1/chat/completions, /chat/completions, and /streaming/chat/completions requests
            if self.path.startswith("/streaming/chat/completions") or self.path.startswith("/v1/streaming/chat/completions") or (self.path == "/chat/completions" and request_data.get("stream") == True):
                 stream = True
            
            self.log_debug(f"do_POST /v1/chat/completions: calling query_gpt4all with messages={messages}, model={model}")
            gpt4all_response = query_gpt4all(messages, model, temperature, top_p, max_tokens, timeout, self.log_debug)
            self.log_debug(f"do_POST /v1/chat/completions: gpt4all_response={gpt4all_response}")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if stream:
                stream_response(self, gpt4all_response, request_data.get("stream_delay", STREAM_DELAY), self.log_debug)
            else:
                self.wfile.write(json.dumps({"text": gpt4all_response}).encode("utf-8"))

        elif self.path.startswith("/v1/completions") or self.path == "/completions" or self.path.startswith("/streaming/completions") or self.path.startswith("/v1/streaming/completions"):
            # Handle /v1/completions, /completions, and /streaming/completions requests
            if self.path.startswith("/streaming/completions") or self.path.startswith("/v1/streaming/completions") or (self.path == "/completions" and request_data.get("stream") == True):
                 stream = True
                 
            self.log_debug(f"do_POST /v1/completions: calling query_gpt4all with messages={messages}, model={model}")
            gpt4all_response = query_gpt4all(messages, model, temperature, top_p, max_tokens, timeout, self.log_debug)
            self.log_debug(f"do_POST /v1/completions: gpt4all_response={gpt4all_response}")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            if stream:
                stream_response(self, gpt4all_response, request_data.get("stream_delay", STREAM_DELAY), self.log_debug)
            else:
                self.wfile.write(json.dumps({"text": gpt4all_response}).encode("utf-8"))
        elif self.path.startswith("/v1/models"):
            # Handle /v1/models requests
            try:
                models = self.get_model_list()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(models).encode("utf-8"))
            except Exception as e:
                self.log_debug(f"Error fetching models: {e}")
                self.send_error(500, str(e))
        elif self.path == "/models":
             # Handle /models requests
            try:
                models = self.get_model_list()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(models).encode("utf-8"))
            except Exception as e:
                self.log_debug(f"Error fetching models: {e}")
                self.send_error(500, str(e))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))

    def get_model_list(self):
        """Fetch the list of available models from GPT4All."""
        self.log_debug("get_model_list: Fetching model list.")
        if self.path.startswith("/v1/"):
            req = urllib.request.Request(GPT4ALL_MODELS_ENDPOINT, headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(GPT4ALL_MODELS_ENDPOINT, headers={"Content-Type": "application/json"}) # Ensure non-/v1 also uses GPT4All

        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                result = response.read().decode("utf-8")
                self.log_debug(f"get_model_list: Model list response: {result}")
                return json.loads(result)
        except Exception as e:
            self.log_debug(f"Error fetching model list: {e}")
            return {"error": f"Failed to fetch models: {e}"}

    def get_model_details(self, model_name):
        """Fetch the details of a specific model from GPT4All."""
        self.log_debug(f"get_model_details: Fetching details for model: {model_name}")
        req = urllib.request.Request(f"{GPT4ALL_MODELS_ENDPOINT}/{model_name}", headers={"Content-Type": "application/json"})

        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                result = response.read().decode("utf-8")
                self.log_debug(f"get_model_details: Model details response: {result}")
                return json.loads(result)
        except Exception as e:
            self.log_debug(f"Error fetching model details: {e}")
            return {"error": f"Failed to fetch model details: {e}"}

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            try:
                # Fetch the model list from GPT4All
                models = self.get_model_list()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(models).encode("utf-8"))
            except Exception as e:
                self.log_debug(f"Error fetching models: {e}")
                self.send_error(500, str(e))
        elif self.path == "/models":
            try:
                # Fetch the model list from GPT4All
                models = self.get_model_list()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(models).encode("utf-8"))
            except Exception as e:
                self.log_debug(f"Error fetching models: {e}")
                self.send_error(500, str(e))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))

def run_server():
    # Allow address reuse to prevent 'Address already in use' errors
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), StreamingHandler) as httpd:
        print(f"Serving on port {PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    try:
        while True:
            time.sleep(1)  # Keep the main thread alive
    except KeyboardInterrupt:
        print("Shutting down server.")
