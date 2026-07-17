"""Typed exception namespace for Local Adventure Engine."""


class LocalAdventureError(Exception):
    """Base exception for expected application errors."""


class ConfigurationError(LocalAdventureError): pass
class WorldValidationError(LocalAdventureError): pass
class ContentParseError(LocalAdventureError): pass
class StateEventValidationError(LocalAdventureError): pass
class StateInvariantError(LocalAdventureError): pass
