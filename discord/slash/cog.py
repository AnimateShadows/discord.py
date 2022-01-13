from .command import ApplicationCommand


class CogMeta(type):
    def __new__(cls, name, bases, attrs):
        slash_commands = []
        for attr in attrs.values():
            if isinstance(attr, ApplicationCommand):
                slash_commands.append(attr)

        attrs["__slash_commands__"] = slash_commands
        return type.__new__(cls, name, bases, attrs)


class Cog(metaclass=CogMeta):
    ...
