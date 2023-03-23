from __future__ import annotations

import base64
import logging
import os

import dotenv
import requests

dotenv.load_dotenv()
server = f"http://{os.getenv('SERVER_IP')}:{os.getenv('SERVER_PORT')}"


class Endpoints():
    """
    Class for commands related with users
    """

    @staticmethod
    def get_soundboard(guild_id) -> list[str] | None:
        """
        Returns list of sounds located on the server for giver id
        """
        url = server + f"/{os.getenv('SERVER_ENDPOINT')}/{guild_id}"
        response = requests.get(url=url, timeout=2)
        if response.status_code != 200:
            logging.warning("Server responded with code: %d", response.status_code)
            return None
        return response.json()["files"]

    @staticmethod
    def upload_audio(guild_id: int, file_name: str, file_data: bytes) -> str:
        """
        Upload bytes data to server
        """
        b64_code = base64.b64encode(file_data)
        headers = {'Content-Type': 'application/json'}
        mp3_json = {"file_name": file_name, "file_data": b64_code.decode('utf-8')}
        url = server + f"/{os.getenv('SERVER_ENDPOINT')}/{guild_id}"
        message = ''
        try:
            response = requests.post(url=url, headers=headers, json=mp3_json, timeout=2)
            if response.status_code == 200:
                message = 'Upload successful!'
            else:
                message = f'Upload failed, server code:{response.status_code}'
        except requests.exceptions.ConnectTimeout:
            message = 'Upload failed, request timed out.'
        return message
