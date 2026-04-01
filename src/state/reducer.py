"""State reducer: dispatch actions to transform state immutably."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from state.store import StateStore

logger = logging.getLogger(__name__)


@dataclass
class Action:
    """An action that describes a state change."""
    type: str
    payload: Any = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Action(type={self.type!r}, payload={self.payload!r})"


ReducerFunc = Callable[[Dict[str, Any], Action], Dict[str, Any]]
MiddlewareFunc = Callable[[Action, "StateReducer"], Optional[Action]]


class StateReducer:
    """Manages action dispatch and state reduction with middleware support."""

    def __init__(self, store: StateStore):
        self.store = store
        self._reducers: Dict[str, ReducerFunc] = {}
        self._middleware: List[MiddlewareFunc] = []
        self._action_log: List[Action] = []
        self._max_log = 200

        # Register built-in reducers
        self._register_builtins()

    def register(self, action_type: str, reducer: ReducerFunc) -> None:
        """Register a reducer function for an action type."""
        self._reducers[action_type] = reducer
        logger.debug("Registered reducer for action: %s", action_type)

    def add_middleware(self, middleware: MiddlewareFunc) -> None:
        """Add middleware that can intercept or transform actions."""
        self._middleware.append(middleware)

    def dispatch(self, action: Action) -> Dict[str, Any]:
        """Dispatch an action through middleware, then reduce state."""
        # Run through middleware chain
        current_action: Optional[Action] = action
        for mw in self._middleware:
            if current_action is None:
                break
            current_action = mw(current_action, self)
        if current_action is None:
            logger.debug("Action %s was cancelled by middleware", action.type)
            return self.store.snapshot()

        # Log the action
        self._action_log.append(current_action)
        if len(self._action_log) > self._max_log:
            self._action_log.pop(0)

        # Reduce
        return self.reduce(current_action)

    def reduce(self, action: Action) -> Dict[str, Any]:
        """Apply an action's reducer to the current state."""
        reducer = self._reducers.get(action.type)
        if reducer is None:
            logger.warning("No reducer registered for action: %s", action.type)
            return self.store.snapshot()

        state = self.store.snapshot()
        try:
            new_state = reducer(state, action)
        except Exception as e:
            logger.error("Reducer error for %s: %s", action.type, e)
            return state

        # Apply changed keys back to store
        for key, value in new_state.items():
            if state.get(key) != value:
                self.store.set(key, value)

        # Handle deleted keys
        for key in state:
            if key not in new_state:
                self.store.delete(key)

        return self.store.snapshot()

    def _register_builtins(self) -> None:
        """Register built-in action reducers."""

        def set_reducer(state: Dict[str, Any], action: Action) -> Dict[str, Any]:
            new = dict(state)
            if isinstance(action.payload, dict):
                key = action.payload.get("key", "")
                value = action.payload.get("value")
                if key:
                    new[key] = value
            return new

        def delete_reducer(state: Dict[str, Any], action: Action) -> Dict[str, Any]:
            new = dict(state)
            key = action.payload
            new.pop(key, None)
            return new

        def merge_reducer(state: Dict[str, Any], action: Action) -> Dict[str, Any]:
            new = dict(state)
            if isinstance(action.payload, dict):
                new.update(action.payload)
            return new

        def reset_reducer(state: Dict[str, Any], action: Action) -> Dict[str, Any]:
            if isinstance(action.payload, dict):
                return dict(action.payload)
            return {}

        self.register("SET", set_reducer)
        self.register("DELETE", delete_reducer)
        self.register("MERGE", merge_reducer)
        self.register("RESET", reset_reducer)

    @property
    def action_history(self) -> List[Action]:
        return list(self._action_log)

    @property
    def registered_actions(self) -> List[str]:
        return list(self._reducers.keys())
