"""Typed exception namespace for Local Adventure Engine."""


class LocalAdventureError(Exception):
    """Base exception for expected application errors."""


class ConfigurationError(LocalAdventureError): pass
class WorldValidationError(LocalAdventureError): pass
class ContentParseError(LocalAdventureError): pass
class DatabaseError(LocalAdventureError): pass
class MigrationError(DatabaseError): pass
class StateEventValidationError(LocalAdventureError): pass
class StateInvariantError(LocalAdventureError): pass
class SessionNotFoundError(LocalAdventureError): pass
class CheckpointNotFoundError(LocalAdventureError): pass
class ConcurrentSessionUpdateError(LocalAdventureError): pass
class ContextBudgetError(LocalAdventureError): pass
class LoreIndexError(LocalAdventureError): pass
class ProposalValidationError(LocalAdventureError): pass


class ModelError(LocalAdventureError):
    """Base class for failures communicating with the configured model."""


class ModelConnectionError(ModelError): pass
class ModelTimeoutError(ModelError): pass
class ModelProtocolError(ModelError): pass
