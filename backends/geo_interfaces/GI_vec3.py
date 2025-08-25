from typing import Union
from ..interface import Attribute, AccessMode, TypeInterfaceDefinition
from ..type_defs import DataType
from .. import type_defs as td

from bpy.types import NodeSocket


#push the i-th component of the vec3 onto the stack
def read_component(operations: list[td.Operation],index: int, variable_name: str):
    
    operations.append(
        td.Operation(
            td.OpType.GET_VAR,
            variable_name,
        )
    )
    operations.append(
        td.Operation(
            td.OpType.CALL_BUILTIN,
            td.NodeInstance("ShaderNodeSeparateXYZ", [], [index], []),
        )
    )
    operations.append(
        td.Operation(
            td.OpType.GET_OUTPUT,
            index,
        )
    )
    
def write_component(operations: list[td.Operation],
    index: int, 
    variable_name: str,
    value: Union[float, NodeSocket]):
    
    if index == 0:  # replace x component
        operations.append(td.Operation(td.OpType.PUSH_VALUE, value))
        read_component(operations, 1, variable_name)
        read_component(operations, 2, variable_name)
    
    elif index == 1:  # replace y component
        read_component(operations, 0, variable_name)
        operations.append(td.Operation(td.OpType.PUSH_VALUE, value))
        read_component(operations, 2, variable_name)
    
    elif index == 2:  # replace z component
        read_component(operations, 0, variable_name)
        read_component(operations, 1, variable_name)
        operations.append(td.Operation(td.OpType.PUSH_VALUE, value))
    
    # create Combine XYZ node
    operations.append(
        td.Operation(
            td.OpType.CALL_BUILTIN,
            td.NodeInstance("ShaderNodeCombineXYZ", [], [0], []),
        )
    )
    
    # bind the variable
    operations.append(
        td.Operation(
            td.OpType.BIND_VAR,
            variable_name
        )
    )


class Vec3ComponentAttribute(Attribute):
    def __init__(self, index: int):

        self.index = index      
        if index == 0:
            self.name = "x"
        elif index == 1:
            self.name = "y"
        elif index == 2:
            self.name = "z"
        else:
            raise ValueError(f"Invalid index: {index}")

        self.return_type = DataType.FLOAT
        self.access_mode = AccessMode.READ_WRITE

    def read(self, operations: list[td.Operation], variable_name: str):
        read_component(operations, self.index, variable_name)
    
    def write(self, operations: list[td.Operation], variable_name: str, value: Union[float, NodeSocket]):
        write_component(operations, self.index, variable_name, value)



Vec3XAttribute = Vec3ComponentAttribute(0)
Vec3YAttribute = Vec3ComponentAttribute(1)
Vec3ZAttribute = Vec3ComponentAttribute(2)

IVec3 = TypeInterfaceDefinition(
    base_type=DataType.VEC3,
    interfaces={
        "x": Vec3XAttribute,
        "y": Vec3YAttribute,
        "z": Vec3ZAttribute,
    }
)
