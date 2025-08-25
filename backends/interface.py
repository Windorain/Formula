from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import Union, Dict, List, Optional, Callable
from .type_defs import DataType


class AccessMode(IntEnum):
    """Property access mode"""
    READ_ONLY = auto()
    WRITE_ONLY = auto()  
    READ_WRITE = auto()
    INTERFACE_ONLY = auto()


class InterfaceType(IntEnum):
    """Interface types"""
    ATTRIBUTE = auto()
    METHOD = auto()
    CONTAINER = auto()


@dataclass
class Interface:
    name: str
    interface_type: InterfaceType
    return_type: Union[DataType, str]
    access_mode: AccessMode
    child_interfaces: Dict[str, 'Interface'] = field(default_factory=dict)

@dataclass
class Attribute(Interface):
    interface_type: InterfaceType = InterfaceType.ATTRIBUTE
    
    def read(self, source: str, target: str):
        raise NotImplementedError(f"read not implemented for {self.return_type}")
    
    def write(self, source: str, target: str, value: str):
        raise NotImplementedError(f"write not implemented for {self.return_type}")

@dataclass
class TypeInterfaceDefinition:
    """Type definition"""
    base_type: DataType
    interfaces: Dict[str, Interface] = field(default_factory=dict)


@dataclass
class TypeRegistry:
    """Type registry"""
    types: Dict[str, TypeInterfaceDefinition] = field(default_factory=dict)
    
    def register_type(self, type_def: TypeInterfaceDefinition) -> None:
        self.types[name] = type_def
    
    def get_type(self, name: str) -> Optional[TypeInterfaceDefinition]:
        return self.types.get(name)
    
    def get_interface(self, type_name: str, interface_name: str) -> None:
        type_def = self.get_type(type_name)
        if type_def:
            return type_def.interfaces.get(interface_name)
        return None


def initialize_type_system():
    """Initialize type system"""
    pass


# Initialize
initialize_type_system()

