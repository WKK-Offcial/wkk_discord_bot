import logging
import os
from pathlib import Path

import dropbox
from dropbox.exceptions import ApiError, AuthError


class DropboxManager:
    """
    Class responsible for connection between the bot and a remote storage service (Dropbox)
    """

    def __init__(self):
        try:
            logging.info("Logging in to dropbox...")
            self.dbx: dropbox.Dropbox = dropbox.Dropbox(oauth2_refresh_token=os.getenv('DROPBOX_REFRESH_TOKEN'),
                                                        app_key=os.getenv('DROPBOX_APP_KEY'),
                                                        app_secret=os.getenv('DROPBOX_APP_SECRET'))
            logging.info("Log in successful!")
        except AuthError:
            logging.error(AuthError)

    def _create_folder(self, remote_folder_name):
        try:
            self.dbx.files_get_metadata(remote_folder_name)
        except LookupError:
            self.dbx.files_create_folder_v2(remote_folder_name)

    def list_folders(self, remote_folder_name) -> list:
        """
        Returns a list of all folders in cloud
        """
        result = self.dbx.files_list_folder(remote_folder_name, recursive=True)
        folder_list = []

        def process_dirs(entries):
            for entry in entries:
                if isinstance(entry, dropbox.files.FolderMetadata):
                    folder_list.append(entry.path_lower)

        process_dirs(result.entries)
        while result.has_more:
            result = self.dbx.files_list_folder_continue(result.cursor)
            process_dirs(result.entries)

        return folder_list

    def download_files_from_folder(self, remote_folder_name):
        """
        Download all files for specified guild
        """
        result = self.dbx.files_list_folder(remote_folder_name, recursive=True)

        file_list = []

        def process_files(entries):
            for entry in entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    file_list.append(entry.path_lower)

        process_files(result.entries)
        while result.has_more:
            result = self.dbx.files_list_folder_continue(result.cursor)
            process_files(result.entries)

        logging.info('Downloading %s folder...', remote_folder_name)
        i = 0
        for file_path in file_list:
            i += 1
            base_path = f'./cache/soundboards/{remote_folder_name}'
            file_name = os.path.basename(file_path)
            try:
                logging.info(file_path)
                Path(base_path).mkdir(parents=True, exist_ok=True)
                destination_path = f'{base_path}/{file_name}'
                if not os.path.exists(destination_path):
                    self.dbx.files_download_to_file(path=file_path, download_path=destination_path)
            except ApiError:
                logging.error(ApiError)
            finally:
                logging.info('Finished folder download')

    def upload_file(self, file_path, remote_folder_name):
        """
        Upload file to cloud
        """
        with open(file_path, "rb") as file:
            file_name = os.path.basename(file_path)
            try:
                self.dbx.files_upload(file.read(), f'/{remote_folder_name}/{file_name}', mute=True)
            except ApiError:
                logging.error(ApiError)

    def download_all(self):
        """
        Download everything in storage
        """
        try:
            folders = self.list_folders('')
            for folder in folders:
                self.download_files_from_folder(folder)
        except ApiError:
            logging.error(ApiError)
