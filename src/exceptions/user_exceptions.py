
class UserException(Exception):
    """
    Base Exception for all exceptions caused by user
    """


class SoundboardTrackNotFound(UserException):
    """
    Exception for when given soundboard id was not found
    """
