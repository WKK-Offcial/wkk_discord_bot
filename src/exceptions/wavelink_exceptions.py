class WavelinkPlayerException(Exception):
    """
    Base Exception for all WavelinkPlayer exceptions
    """


class YoutubeTrackNotFound(WavelinkPlayerException):
    """
    Exception for when WavelinkPlayer couldn't find a track
    """


class UnexpectedPlayableType(WavelinkPlayerException):
    """
    Exception for when WavelinkPlayer returned unexpected Playable type
    """
