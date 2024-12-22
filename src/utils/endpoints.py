from __future__ import annotations

import base64
import logging
import os
from typing import Optional

import dotenv
import requests

# Load environment variables
dotenv.load_dotenv()

SERVER_URL = f"http://{os.getenv('SERVER_IP')}:{os.getenv('SERVER_PORT')}"
ENDPOINT = os.getenv('SERVER_ENDPOINT')


class Endpoints:
    """
    Handles HTTP communication with the audio server.
    """

    @staticmethod
    def get_soundboard(guild_id: int) -> Optional[list[str]]:
        """
        Retrieves a list of sound files from the server for the given guild ID.

        Args:
            guild_id (int): The ID of the guild.

        Returns:
            Optional[list[str]]: A list of sound file names or None if the request fails.
        """
        url = f"{SERVER_URL}/{ENDPOINT}/{guild_id}"
        try:
            response = requests.get(url=url, timeout=2)
            if response.status_code == 200:
                return response.json().get("files", [])
            logging.warning("Server responded with status code: %d", response.status_code)
        except requests.RequestException as e:
            logging.error("Error fetching soundboard: %s", e)
        return None

    @staticmethod
    def upload_audio(guild_id: int, file_name: str, file_data: bytes) -> str:
        """
        Uploads audio data to the server.

        Args:
            guild_id (int): The ID of the guild.
            file_name (str): The name of the file to upload.
            file_data (bytes): The file data in bytes.

        Returns:
            str: A message indicating the result of the upload operation.
        """
        url = f"{SERVER_URL}/{ENDPOINT}/{guild_id}"
        b64_code = base64.b64encode(file_data).decode('utf-8')
        headers = {'Content-Type': 'application/json'}
        payload = {"file_name": file_name, "file_data": b64_code}

        try:
            response = requests.post(url=url, headers=headers, json=payload, timeout=2)
            if response.status_code == 200:
                return "Upload successful!"
            return f"Upload failed, server responded with status code: {response.status_code}"
        except requests.ConnectTimeout:
            return "Upload failed, connection timed out."
        except requests.ReadTimeout:
            return "Upload failed, server took too long to respond."
        except requests.RequestException as e:
            logging.error("Error during file upload: %s", e)
            return "Upload failed due to an unexpected error."
