from typing import cast

import bpy
from bpy.types import Node, NodeSocket

from .backends.type_defs import (
    CompiledFunction,
    CompiledNodeGroup,
    DataType,
    NodeInstance,
    Operation,
    OpType,
    ValueType,
)


class Interpreter:
    def __init__(self, tree: bpy.types.NodeTree) -> None:
        self.tree = tree
        self.stack: list[ValueType | NodeSocket | list[NodeSocket]] = []
        # The nodes that we added
        self.nodes: list[Node] = []
        # Inner node trees of node groups that we have created.
        # TODO: Fill this with existing node trees in the blend file.
        self.node_group_trees: dict[str, bpy.types.NodeTree] = {}
        # Variables in the form of output sockets
        self.variables: dict[str, ValueType | NodeSocket | list[NodeSocket]] = {}
        self.function_outputs: list[NodeSocket | None] = []

    def operation(self, operation: Operation):
        op_type = operation.op_type
        op_data = operation.data
        assert (
            OpType.END_OF_STATEMENT.value == 14
        ), "Exhaustive handling of Operation types."
        if op_type == OpType.PUSH_VALUE:
            self.stack.append(op_data)
        elif op_type == OpType.CREATE_VAR:
            assert isinstance(op_data, str), "Variable name should be a string."
            socket = self.stack.pop()
            assert isinstance(
                socket, (NodeSocket, list, int)
            ), "Create var expects a node socket or struct or loop index."
            if isinstance(socket, list):
                socket = cast(list[NodeSocket], socket)
            self.variables[op_data] = socket
        elif op_type == OpType.GET_VAR:
            assert isinstance(op_data, str), "Variable name should be a string."
            self.stack.append(self.variables[op_data])
        elif op_type == OpType.GET_OUTPUT:
            assert isinstance(op_data, int), "Bug in type checker, index should be int."
            index = op_data
            struct = self.stack.pop()
            assert isinstance(
                struct, list
            ), "Bug in type checker, GET_OUTPUT only works on structs."
            # Index order is reversed
            self.stack.append(struct[-index - 1])
        elif op_type == OpType.SET_OUTPUT:
            assert isinstance(op_data, tuple), "Data should be tuple of index and value"
            index, value = op_data
            self.nodes[-1].outputs[index].default_value = value  # type: ignore
        elif op_type == OpType.SET_FUNCTION_OUT:
            assert isinstance(op_data, int), "Data should be an index"
            socket = self.stack.pop()
            assert isinstance(socket, NodeSocket)
            self.function_outputs[op_data] = socket
        elif op_type == OpType.SPLIT_STRUCT:
            struct = self.stack.pop()
            assert isinstance(
                struct, list
            ), "Bug in type checker, GET_OUTPUT only works on structs."
            self.stack += struct
        elif op_type == OpType.CALL_FUNCTION:
            assert isinstance(op_data, CompiledFunction), "Bug in type checker."
            args = self.get_args(self.stack, len(op_data.inputs))
            # Store state outside function, and prepare state in function
            outer_vars = self.variables
            self.variables = {}
            for name, arg in zip(op_data.inputs, args):
                self.variables[name] = arg
            outer_function_outputs = self.function_outputs
            self.function_outputs = [None for _ in range(op_data.num_outputs)]
            outer_stack = self.stack
            self.stack = []
            # Execute function
            for operation in op_data.body:
                self.operation(operation)
            # Restore state outside function
            self.stack = outer_stack
            if len(self.function_outputs) == 1:
                output = self.function_outputs[0]
                assert isinstance(output, NodeSocket)
                self.stack.append(output)
            elif len(self.function_outputs) > 1:
                for output in self.function_outputs:
                    assert isinstance(output, NodeSocket)
                self.stack.append(list(reversed(self.function_outputs)))  # type: ignore
            self.function_outputs = outer_function_outputs
            self.variables = outer_vars
        elif op_type == OpType.CALL_NODEGROUP:
            assert isinstance(op_data, CompiledNodeGroup), "Bug in type checker."
            args = self.get_args(self.stack, len(op_data.inputs))
            self.execute_node_group(op_data, args)
        elif op_type == OpType.CALL_BUILTIN:
            assert isinstance(op_data, NodeInstance), "Bug in compiler."
            args = self.get_args(self.stack, len(op_data.inputs))
            node = self.add_builtin(
                op_data,
                args,
            )
            outputs = op_data.outputs
            if len(outputs) == 1:
                self.stack.append(node.outputs[outputs[0]])
            elif len(outputs) > 1:
                self.stack.append([node.outputs[o] for o in reversed(outputs)])
            self.nodes.append(node)
        elif op_type == OpType.RENAME_NODE:
            self.nodes[-1].label = op_data
        elif op_type == OpType.CREATE_NODE_GROUP:
            assert isinstance(op_data, CompiledNodeGroup), "Bug in type checker."
            self.create_node_group(op_data)
        elif op_type == OpType.CREATE_REPEAT_ZONE:
            # Get iterations count from stack (compiled expression result)
            iterations = self.stack.pop()
            if isinstance(iterations, int):
                self.create_repeat_zone(iterations)
            elif isinstance(iterations, NodeSocket):
                # Pass NodeSocket directly to create_repeat_zone for proper connection
                self.create_repeat_zone(iterations)
            else:
                print(f"Error: Invalid iterations count type: {type(iterations)}")
                return
        elif op_type == OpType.REPEAT_BODY:
            assert isinstance(op_data, list), "Repeat body should be a list of operations."
            self.execute_repeat_body(op_data)
        elif op_type == OpType.END_OF_STATEMENT:
            self.stack = []
        else:
            print(f"Need implementation of {op_type}")
            raise NotImplementedError

    def get_args(self, stack: list, num_args: int) -> list[ValueType]:
        if num_args == 0:
            return []
        args = stack[-num_args:]
        stack[:] = stack[:-num_args]
        return args

    def add_builtin(
        self, node_info: NodeInstance, args: list[ValueType]
    ) -> bpy.types.Node:
        tree = self.tree
        node = tree.nodes.new(type=node_info.key)
        for name, value in node_info.props:
            setattr(node, name, value)
        for i, input_index in enumerate(node_info.inputs):
            arg = args[i]
            if isinstance(arg, bpy.types.NodeSocket):
                tree.links.new(arg, node.inputs[input_index])
            elif arg is not None:
                node.inputs[input_index].default_value = arg  # type: ignore
        return node

    @staticmethod
    def data_type_to_socket_type(dtype: DataType) -> str:
        if dtype == DataType.BOOL:
            return "NodeSocketBool"
        elif dtype == DataType.INT:
            return "NodeSocketInt"
        elif dtype == DataType.FLOAT:
            return "NodeSocketFloat"
        elif dtype == DataType.RGBA:
            return "NodeSocketColor"
        elif dtype == DataType.VEC3:
            return "NodeSocketVector"
        elif dtype == DataType.GEOMETRY:
            return "NodeSocketGeometry"
        elif dtype == DataType.STRING:
            return "NodeSocketString"
        elif dtype == DataType.SHADER:
            return "NodeSocketShader"
        elif dtype == DataType.OBJECT:
            return "NodeSocketObject"
        elif dtype == DataType.IMAGE:
            return "NodeSocketImage"
        elif dtype == DataType.COLLECTION:
            return "NodeSocketCollection"
        elif dtype == DataType.TEXTURE:
            return "NodeSocketTexture"
        elif dtype == DataType.MATERIAL:
            return "NodeSocketMaterial"
        elif dtype == DataType.ROTATION:
            return "NodeSocketRotation"
        else:
            assert False, "Unreachable"

    @staticmethod
    def socket_bl_idname_to_repeat_type(bl_idname: str) -> str:
        """Convert NodeSocket bl_idname to repeat zone socket_type enum"""
        mapping = {
            "NodeSocketBool": "BOOLEAN",
            "NodeSocketInt": "INT", 
            "NodeSocketFloat": "FLOAT",
            "NodeSocketColor": "RGBA",
            "NodeSocketVector": "VECTOR",
            "NodeSocketGeometry": "GEOMETRY",
            "NodeSocketString": "STRING",
            "NodeSocketShader": "SHADER",
            "NodeSocketObject": "OBJECT",
            "NodeSocketImage": "IMAGE",
            "NodeSocketCollection": "COLLECTION",
            "NodeSocketTexture": "TEXTURE",
            "NodeSocketMaterial": "MATERIAL",
            "NodeSocketRotation": "ROTATION",
        }
        return mapping.get(bl_idname, "FLOAT")  # Default to FLOAT if unknown

    def execute_node_group(self, node_group: CompiledNodeGroup, args: list[ValueType]):
        if node_group.name in self.node_group_trees:
            node_tree = self.node_group_trees[node_group.name]
        else:
            # Create the node group's inner tree:
            node_tree = bpy.data.node_groups.new(node_group.name, self.tree.bl_idname)

            for input in node_group.inputs:
                in_socket = node_tree.interface.new_socket(
                    input.name,
                    in_out="INPUT",
                    socket_type=self.data_type_to_socket_type(input.dtype),
                )
                if input.value is not None:
                    in_socket.default_value = input.value  # type: ignore
            for output in node_group.outputs:
                out_socket = node_tree.interface.new_socket(
                    output.name,
                    in_out="OUTPUT",
                    socket_type=self.data_type_to_socket_type(output.dtype),
                )
                if output.value is not None:
                    out_socket.default_value = output.value  # type: ignore
            group_input = node_tree.nodes.new("NodeGroupInput")
            group_output = node_tree.nodes.new("NodeGroupOutput")

            # Store state outside node group, and prepare state in node group
            outer_tree = self.tree
            self.tree = node_tree
            outer_vars = self.variables
            self.variables = {}
            for socket in group_input.outputs:
                self.variables[socket.name] = socket
            outer_function_outputs = self.function_outputs
            self.function_outputs = [None for _ in range(len(node_group.outputs))]
            outer_stack = self.stack
            self.stack = []
            # Execute node group
            for operation in node_group.body:
                self.operation(operation)

            # Connect to the group outputs
            for index, foutput in enumerate(self.function_outputs):
                if isinstance(foutput, NodeSocket):
                    node_tree.links.new(foutput, group_output.inputs[index])
                elif foutput is not None:
                    group_output.inputs[index].default_value = foutput  # type: ignore

            # Restore state outside node group
            self.stack = outer_stack
            self.function_outputs = outer_function_outputs
            self.variables = outer_vars
            self.tree = outer_tree
            # Store it so we don't recreate it if called multiple times.
            self.node_group_trees[node_group.name] = node_tree

        # Add the group and connect the arguments
        group_name = (
            "GeometryNodeGroup"
            if self.tree.bl_idname == "GeometryNodeTree"
            else "ShaderNodeGroup"
        )
        node = self.tree.nodes.new(group_name)
        node = cast(bpy.types.NodeGroup, node)
        node.node_tree = node_tree
        for i, arg in enumerate(args):
            if isinstance(arg, NodeSocket):
                self.tree.links.new(arg, node.inputs[i])
            elif arg is not None:
                node.inputs[i].default_value = arg  # type: ignore
        self.nodes.append(node)

        if len(node.outputs) == 1:
            self.stack.append(node.outputs[0])
        elif len(node.outputs) > 1:
            self.stack.append(
                [node.outputs[i] for i in reversed(range(len(node.outputs)))]
            )

    def create_repeat_zone(self, iterations):
        """Create a repeat zone with input and output nodes"""
        input_node = self.tree.nodes.new(type="GeometryNodeRepeatInput")
        output_node = self.tree.nodes.new(type="GeometryNodeRepeatOutput")
        
        input_node.pair_with_output(output_node)
        
        # Remove default geometry interfaces to simplify slot management
        if hasattr(input_node, 'repeat_items') and len(input_node.repeat_items) > 1:
            input_node.repeat_items.remove(input_node.repeat_items[1])  # Remove geometry
        
        if hasattr(output_node, 'repeat_items') and len(output_node.repeat_items) > 0:
            output_node.repeat_items.remove(output_node.repeat_items[0])  # Remove geometry
        
        # Connect iterations to input node
        if isinstance(iterations, NodeSocket):
            # Connect variable to iterations input
            if len(input_node.inputs) > 0:
                self.tree.links.new(iterations, input_node.inputs[0])
        elif isinstance(iterations, int):
            # Set literal value
            if len(input_node.inputs) > 0:
                input_node.inputs[0].default_value = iterations
        
        self.current_repeat_zone = {
            'input_node': input_node,
            'output_node': output_node,
            'iterations': iterations,
            'captured_vars': {}
        }
        
        self.nodes.extend([input_node, output_node])

    def execute_repeat_body(self, body_operations: list):
        """Execute repeat body and connect variables"""
        if not hasattr(self, 'current_repeat_zone'):
            return
            
        repeat_zone = self.current_repeat_zone
        input_node = repeat_zone['input_node']
        output_node = repeat_zone['output_node']
        
        # Analyze loop body to identify variables that need capture
        loop_vars = set()
        for operation in body_operations:
            if operation.op_type == OpType.CREATE_VAR:
                loop_vars.add(operation.data)  # Variable name
        
        # Compare with external variables and capture only those that exist
        captured_vars = {}
        for name in loop_vars:
            if name in self.variables and isinstance(self.variables[name], NodeSocket):
                captured_vars[name] = self.variables[name]
        
        # Set iterations - now handled by node connections
        # if len(input_node.inputs) > 0:
        #     input_node.inputs[0].default_value = repeat_zone['iterations']
        
        # Create input/output slots for captured variables
        for i, (name, socket) in enumerate(captured_vars.items()):
            # Convert socket type to repeat zone enum
            socket_type = self.socket_bl_idname_to_repeat_type(socket.bl_idname)
            
            # Add input slot
            if hasattr(input_node, 'repeat_items'):
                new_input = input_node.repeat_items.new(
                    socket_type=socket_type,
                    name=name
                )
            
            # Add output slot  
            if hasattr(output_node, 'repeat_items'):
                new_output = output_node.repeat_items.new(
                    socket_type=socket_type,
                    name=name
                )
        
        # Update node tree to rebuild sockets
        self.tree.update_tag()
        
        # Connect captured variables to input node inputs (external connections)
        # Skip first input (iterations)
        for i, (name, socket) in enumerate(captured_vars.items()):
            if i + 1 < len(input_node.inputs):
                self.tree.links.new(socket, input_node.inputs[i + 1])
        
        # Connect variables to input node outputs (internal connections)
        # Skip first output (iterations)
        for i, (name, _) in enumerate(captured_vars.items()):
            if i + 1 < len(input_node.outputs):
                self.variables[name] = input_node.outputs[i + 1]
        
        # Execute body operations with proper variable connections
        for operation in body_operations:
            self.operation(operation)
        
        # Connect loop body results to output node inputs
        # This ensures data flows from the loop body to the output
        for i, (name, _) in enumerate(captured_vars.items()):
            if i < len(output_node.inputs):
                # Get the current value of the variable after loop execution
                if name in self.variables:
                    var_value = self.variables[name]
                    if isinstance(var_value, NodeSocket):
                        self.tree.links.new(var_value, output_node.inputs[i])
        
        # Connect output variables from repeat zone
        # No need to skip, geometry was removed
        for i, (name, _) in enumerate(captured_vars.items()):
            if i < len(output_node.outputs):
                self.variables[name] = output_node.outputs[i]
        
        delattr(self, 'current_repeat_zone')
