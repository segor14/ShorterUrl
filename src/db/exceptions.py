class BaseRepositoryException(Exception):
    ...


class BaseUserRepositoryException(BaseRepositoryException):
    ...


class UserAlreadyExistsException(BaseUserRepositoryException):
    ...


class UserNotFound(BaseUserRepositoryException):
    ...


class LinkNotFound(BaseRepositoryException):
    ...


class LinkAlreadyExists(BaseRepositoryException):
    def __init__(self, message: str = "Link already exists"):
        self.message = message
        super().__init__(self.message)
