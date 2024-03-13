import logging
from exceptions.user_exceptions import SoundboardTrackNotFound
from exceptions.wavelink_exceptions import UnexpectedPlayableType, YoutubeTrackNotFound


class ExceptionHandler(Exception):
    def handle(self, err) -> str:
        logging.error(err)
        if isinstance(err, YoutubeTrackNotFound):
            return "Youtube track not found!"
        if isinstance(err, SoundboardTrackNotFound):
            return "Soundboard track not found!"
        if isinstance(err, UnexpectedPlayableType):
            return "Server returned unexpected type!"
        if isinstance(err, SyntaxError):
            return "No argument passed!"
        if isinstance(err, IndexError):
            return "No such index in soundboard!"
        if isinstance(err, TypeError):
            return "Type error!"
        return "Unexpected error occured!"
