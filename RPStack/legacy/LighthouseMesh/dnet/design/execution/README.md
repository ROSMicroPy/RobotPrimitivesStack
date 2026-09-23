# Execution System Overview

This folder documents the execution paths that work together:

- A DSL-to-IR compiler (`dsl_to_ir.py`)
- An IR schema + validator (`execution_ir.py`)
- An execution runtime (`executionEngine.py`) that supports both classic node flows and IR execution
- Example entry points (`example_usage.py`)

## 1. DSL Compiler: `dsl_to_ir.py`

`dsl_to_ir.py` converts a user workflow DSL into a strongly typed `ExecutionIr` graph.

### Input Shape

- Top level:
  - `version` (supports `1`, `1.0`, `1.0.0`)
  - `actor` (string)
  - `rules` (non-empty array)
- Each `rule` has:
  - `id` (required string)
  - `on.event.in` (required list of event names)
  - `start` (at least one action)
  - `stop` (optional; defaults to `stepper.stop`)
  - `timeout` (optional; defaults to `stepper.stop` with reason `timeout`)
  - `until` (optional branch conditions)

### Key Compiler Steps

`compile_dsl_to_ir()`:

1. Validates payload type and version.
2. Iterates every rule and calls `compile_rule(rule)`.
3. Assembles all compiled nodes into one graph payload.
4. Sets graph entry to the first rule's `_wait_start` node and exposes all rule entry nodes.

`compile_rule(rule)` builds these node patterns per rule:

- `WAIT_EVENT` node: `<rule>_wait_start`
  - Waits for every event in `on.event.in`.
  - On `ok` transitions to first start action node.
- Action chain for `start`:
  - `<rule>_start_action_0`, `_1`, ...
  - Each node executes one action and transitions to the next.
- `WAIT_MULTI` node: `<rule>_wait_stop`
  - Built from `until` conditions.
  - Supports:
    - `on`: event wait condition
    - `timeout`: ms timeout
- `stop` action chain:
  - `<rule>_stop`, `<rule>_stop_1`, ...
- `timeout` action chain:
  - `<rule>_timeout`, `<rule>_timeout_1`, ...
- Terminal node: `<rule>_done` (`END` with `{ "status": "idle" }`)

### Coercion And Validation

The compiler normalizes incoming DSL with small helpers:

- `_coerce_name`
- `_coerce_event_name`
- `_coerce_action`
- `_coerce_action_list`

Malformed shapes raise `ValueError`.

## 2. IR Data Model: `execution_ir.py`

Defines schema classes for runtime-safe execution graphs:

- `ExecutionIr` with:
  - `schema_version`
  - `graph`
- `Graph` with:
  - `id`, `kind`, `entry`, `nodes`
  - optional `entry_nodes`
  - optional `correlation_mode`
- Node types:
  - `WAIT_EVENT`, `ACTION`, `WAIT_MULTI`, `EMIT`, `PARALLEL`, `END`

Validation behavior is strict:

- Duplicate node IDs are rejected.
- Entry nodes must exist in the node map.
- All transition targets must exist.
- `WAIT_MULTI` must have at least one option.

`validate_execution_ir(payload)` is the canonical entry for converting dict payloads into typed `ExecutionIr`.

## 3. Runtime Execution: `executionEngine.py`

This module contains:

- a classic event-driven flow engine (`ExecutionEngine` / `Node` / `EventManager`)
- an IR extension (`IrExecutionEngine`)

### Event Basics

- `EventManager` keeps subscribers per event name.
- `Event` includes `name`, `parameters`, `timestamp`, and `event_id`.
- Subscribers get invoked asynchronously in background threads.

### Classic Node Flow

- `Node` supports one action callback, success/failure links, child nodes, and event behavior.
- `ExecutionEngine.execute_flow(start_node)` runs a graph by repeatedly walking `get_next_node`.
- `execute_flow_async` starts it in a thread.
- `publish_event` pushes events into the manager so waiting nodes can continue.

### IR Runtime

`IrExecutionEngine` reuses the base event model.

Workflow:

1. `run_ir(ir_payload, block=False)` loads and validates IR, then starts entry threads.
2. `_run_ir_graph(graph, entry, session_id)` walks nodes and dispatches behavior by kind.
3. Action handlers are registered with `register_action(name, handler)`.
4. `stop()` disables IR execution and joins IR threads before stopping base engine behavior.

## 4. Example Coverage: `example_usage.py`

Contains runnable demonstrations for:

- linear success/failure flow
- parallel child execution
- sequential child execution
- event-driven wait/trigger flow
- multiple consumer threads triggered by repeated event publication

## Mental Model

- `dsl_to_ir.py`: authoring layer
- `execution_ir.py`: contract and validation layer
- `executionEngine.py`: runtime layer
- `example_usage.py`: examples for the legacy flow runtime
