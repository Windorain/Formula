from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import Union, Dict, Optional
from .type_defs import DataType
from bpy.types import NodeSocket
from . import type_defs as td

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
    return_type: Union[DataType, str]
    access_mode: AccessMode
    interface_type: InterfaceType = field(default=InterfaceType.ATTRIBUTE)
    child_interfaces: Dict[str, 'Interface'] = field(default_factory=dict)

@dataclass
class Attribute(Interface):
    
    def read(self, operations: list[td.Operation], variable_name: str):
        raise NotImplementedError(f"read not implemented for {self.return_type}")
    
    def write(self, operations: list[td.Operation], variable_name: str, value: Union[float, NodeSocket]):
        raise NotImplementedError(f"write not implemented for {self.return_type}")

@dataclass
class TypeInterfaceDefinition:
    """Type definition"""
    base_type: DataType
    interfaces: Dict[str, Interface] = field(default_factory=dict)

    def get_interface(self, interface_name: str) -> Union[Interface, None]:
        return self.interfaces.get(interface_name)

    def has_interface(self, interface_name: str) -> bool:
        return interface_name in self.interfaces


@dataclass
class TypeInterfaceRegistry:
    """Type registry"""
    types: Dict[DataType, TypeInterfaceDefinition] = field(default_factory=dict)
    
    def register_type(self, type_def: TypeInterfaceDefinition) -> None:
        self.types[type_def.base_type] = type_def
    
    def get_type(self, type:DataType) -> Optional[TypeInterfaceDefinition]:
        return self.types.get(type)
    
    def get_interface(self, type:DataType, interface_name: str) -> None:
        type_def = self.get_type(type)
        if type_def:
            return type_def.interfaces.get(interface_name)
        return None

    def initialize_interface_system_geometry(self):
        from .geo_interfaces import GI_vec3
        self.register_type(GI_vec3.IVec3)

    def initialize_interface_system_shader(self):
        pass

    