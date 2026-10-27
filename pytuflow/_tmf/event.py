import itertools
import typing

from .misc.append_dict import AppendDict
from .misc.case_insensitive_dict import CaseInsDict


class EventDatabase(CaseInsDict):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inputs = []

    def __setitem__(self, key, value):
        if key in self:
            self[key].update(value)
        else:
            super().__setitem__(key, value)

    def __bool__(self):
        return bool(self.keys()) or bool(self.inputs)

    def update(self, m, /, **kwargs):
        """Update the event database with another mapping or keyword arguments."""
        for key, value in m.items():
            self[key] = value
        for key, value in kwargs.items():
            self[key] = value
        if hasattr(m, 'inputs'):
            self.inputs.extend(m.inputs)
        if hasattr(kwargs, 'inputs'):
            self.inputs.extend(kwargs.inputs)
        return self

    def copy(self):
        """Return a shallow copy of the EventDatabase."""
        new_db = EventDatabase()
        if _builtin_copy_source(self):
            # Plain values have no copy callbacks. Rebuild the index rather than
            # trusting one left stale by inherited dict operations such as pop.
            values = {key: value.copy() for key, value in self.items()}
            key_lower = {key.lower(): key for key in values}
            if len(key_lower) == len(values):
                dict.update(new_db, values)
                new_db._key_lower = key_lower
                new_db.inputs = self.inputs.copy()
                return new_db
            # Constructor-supplied case aliases must still merge in source order.
        for key, value in self.items():
            new_db[key] = value.copy() if isinstance(value, dict) else value
        new_db.inputs = self.inputs.copy()
        return new_db

    def event_variables(self) -> AppendDict:
        d = AppendDict()
        for _key, val in self.items():  # noqa: PERF102 - items() is an append-accounting extension hook.
            for k, v in val.items():
                d[k] = v
        return d

    def event_combinations(self) -> typing.Generator[tuple[tuple[str, str]], None, None]:
        combs = []
        for event_var, event_vals in self.event_variables().items():
            if not isinstance(event_vals, list):
                event_vals = [event_vals]
            combs.append(list(itertools.product([event_var], event_vals)))
        combs = list(itertools.product(*combs))
        yield from combs


# event_variables() is called during deferred input construction and delegates
# to items(). Keep the original attribute access and both callbacks available
# for a descriptor-free append-accounting proof.
_EVENT_DATABASE_APPEND_ATTRIBUTES = (
    ('event_variables', EventDatabase.event_variables),
    ('items', EventDatabase.items),
    ('__getattribute__', EventDatabase.__getattribute__),
    ('__getattr__', None),
    ('__dict__', CaseInsDict.__dict__['__dict__']),
)
_EVENT_DATABASE_APPEND_MRO = EventDatabase.__mro__


# Copy can bypass insertion/normalisation only for the original classes and
# callback-free storage. Extensions keep the established insertion loop. Ignore
# copy itself so a diagnostic wrapper can delegate without disabling the proof.
_EVENT_DATABASE_COPY_TYPE = EventDatabase
_EVENT_DATABASE_COPY_CLASSES = tuple(
    (cls, cls.__mro__, tuple(cls.__dict__.items()))
    for cls in (EventDatabase, CaseInsDict)
)


def _builtin_copy_source(source: EventDatabase) -> bool:
    return (
        type(source) is _EVENT_DATABASE_COPY_TYPE
        and EventDatabase is _EVENT_DATABASE_COPY_TYPE
        and dict.__len__(source) > 0
        and all(
            cls.__mro__ == mro
            and len(cls.__dict__) == len(attributes)
            and all(
                cls.__dict__.get(name) is value
                for name, value in attributes
                if cls is not _EVENT_DATABASE_COPY_TYPE or name != 'copy'
            )
            for cls, mro, attributes in _EVENT_DATABASE_COPY_CLASSES
        )
        and vars(source).keys() == {'_key_lower', 'inputs'}
        and type(source.inputs) is list
        and all(type(key) is str and type(value) is dict for key, value in source.items())
    )
