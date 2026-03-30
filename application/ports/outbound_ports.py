# This file will contain the outbound ports for the application.
from abc import ABC, abstractmethod

class ILLMProvider(ABC):
    pass

class IStorageProvider(ABC):
    pass

class IValidationProvider(ABC):
    pass
