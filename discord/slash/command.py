from ..user import User
from ..member import Member
from ..role import Role
from ..channel import (
    TextChannel,
    DMChannel,
    VoiceChannel,
    CategoryChannel,
    StoreChannel,
    Thread,
    StageChannel,
)
from ..message import Message

import inspect
from typing import Union


class Range:
    def __init__(self, min, max):
        self.min = min
        self.max = max

    def __class_getitem__(cls, args):
        if len(args) == 1:
            max = args[0]
            min = 0
        else:
            min = args[0]
            max = args[1]
        return cls(min, max)


class OptionChoice:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def to_dict(self):
        return {"name": self.name, "value": self.value}


class Option:
    def __init__(self, **kwargs):
        self.type = kwargs.pop("type")
        self.name = kwargs.pop("name")
        self.description = kwargs.pop("description")
        self.required = kwargs.pop("required", False)

        if "choices" in kwargs:
            self.choices = [c.to_dict() for c in kwargs.pop("choices")]
        else:
            self.choices = None
        
        if "options" in kwargs:
            self.options = [o.to_dict() for o in kwargs.pop("options")]
        else:
            self.options = None

        self.min_value = kwargs.pop("min_value", None)
        self.max_value = kwargs.pop("max_value", None)

        if "channel_types" in kwargs:
            self.channel_types = [c.type.value for c in kwargs.pop("channel_types")]
        else:
            self.channel_types = None

        self.autocomplete_enabled = "autocomplete" in kwargs
        self.autocomplete = kwargs.pop("autocomplete", None)

        self.subcommand_callback = kwargs.pop("subcommand_callback", None)

    def __repr__(self):
        return f"Option<type={self.type} name={self.name!r} description={self.description!r} required={self.required} choices={self.choices!r} min_value={self.min_value} max_value={self.max_value} channel_types={self.channel_types} autocomplete={self.autocomplete_enabled}>"

    def to_dict(self):
        data = {
            "type": self.type,
            "description": self.description,
            "name": self.name,
            "required": self.required,
        }

        for item in ("options", "choices", "min_value", "max_value", "channel_types"):
            if getattr(self, item) is not None:
                data[item] = getattr(self, item)

        data["autocomplete"] = self.autocomplete_enabled
        return data

def resolve_user(interaction, option):
    if isinstance(option, dict):
        value = option["value"]
    else:
        value = option

    data = interaction.data
    user_data = data["resolved"]["users"][value]
    if value in data["resolved"]["members"]:
        member_data = data["resolved"]["members"][value]
        member_data["user"] = user_data

        return Member(data=member_data, guild=interaction.guild, state=interaction._state)
    else:
        return User(data=user_data, state=interaction._state)

def resolve_role(interaction, option):
    data = interaction.data
    role_data = data["resolved"]["roles"][option["value"]]
    return Role(guild=interaction.guild, state=interaction._state, data=role_data)

def resolve_message(interaction, value):
    message_data = interaction.data["resolved"]["messages"][value]
    return Message(state=interaction._state, channel=interaction.channel, data=message_data)

class ApplicationCommand:
    def __init__(self, func, **kwargs):
        self.callback = func

        self.type = kwargs.pop("type", 1)
        self.name = kwargs.pop("name")
        self.description = kwargs.pop("description", None)
        self.default_permission = kwargs.pop("default_permission", True)

        self.permissions = kwargs.pop("permissions", None)
        self.options = kwargs.pop("options", None)

        self.guild_id = kwargs.pop("guild_id", None)

    def __repr__(self):
        return f"ApplicationCommand<type={self.type} name={self.name!r} description={self.description!r} options={self.options}>"

    def to_dict(self):
        data = {
            "type": self.type,
            "name": self.name,
            "default_permission": self.default_permission,
        }

        if self.description is not None:
            data["description"] = self.description

        if self.options is not None and self.options:
            data["options"] = [o.to_dict() for o in self.options]

        return data
    
    def command(self, **kwargs):
        def func(func):
            if hasattr(func, "__slash_options__"):
                kwargs["options"] = func.__slash_options__
            kwargs["type"] = 1
            kwargs["subcommand_callback"] = func

            option = Option(**kwargs)
            if self.options is None:
                self.options = []

            self.options.append(option)
            return option
        return func

    async def resolve_options(self, interaction):
        data = interaction.data 

        options = []
        subcommand_name = None

        for option in data["options"]:
            if option["type"] == 1:
                subcommand_name = option["name"]
                options = option["options"]
                break
            else:
                options.append(option)
        
        resolved_options = {}
        for option in options:
            if option["type"] in (3, 4, 5, 10):
                resolved_options[option["name"]] = option["value"]

            elif option["type"] == 6:
                resolved_options[option["name"]] = resolve_user(interaction, option)

            elif option["type"] == 7:
                channel = interaction.guild.get_channel(int(option["value"]))
                if channel is None:
                    channel = await interaction.guild.fetch_channel(int(option["value"]))
                
                resolved_options[option["name"]] = channel
            
            elif option["type"] == 8:
                resolved_options[option["name"]] = resolve_role(interaction, option)
            
            elif option["type"] == 9:
                if "users" in data["resolved"] and option["value"] in data["resolved"]["users"]:
                    resolved_options[option["name"]] = resolve_user(interaction, option)
                else:
                    resolved_options[option["name"]] = resolve_role(interaction, option)

        return subcommand_name, resolved_options


def option(name, **kwargs):
    opt_name = name

    def inner(func):
        sig = inspect.signature(func)

        for pname, param in sig.parameters.items():
            if pname == opt_name:
                if not "required" in kwargs:
                    kwargs["required"] = not param.default == inspect.Parameter.default  # type: ignore

                if param.annotation == inspect.Parameter.default:  # type: ignore
                    annotation = str
                else:
                    annotation = param.annotation  # type: ignore

                if isinstance(annotation, Range):
                    kwargs["type"] = 4
                    kwargs["min_value"] = annotation.min
                    kwargs["max_value"] = annotation.max

                elif not "type" in kwargs:
                    types = {
                        str: 3,
                        int: 4,
                        bool: 5,
                        User: 6,
                        Member: 6,
                        TextChannel: 7,
                        VoiceChannel: 7,
                        StageChannel: 7,
                        Thread: 7,
                        DMChannel: 7,
                        CategoryChannel: 7,
                        StoreChannel: 7,
                        Role: 8,
                        Union[Role, Member]: 9,
                        Union[Role, User]: 9,
                        float: 10,
                    }
                    opt_type = types.get(annotation, str)
                    kwargs["type"] = opt_type

                kwargs["name"] = pname
                break
        else:
            raise ValueError(f"no such parameter '{opt_name}'")

        if not hasattr(func, "__slash_options__"):
            setattr(func, "__slash_options__", list())
        func.__slash_options__.append(Option(**kwargs))
        return func

    return inner


def slash_command(**kwargs):
    def inner(func):
        kwargs["type"] = 1

        if hasattr(func, "__slash_options__"):
            kwargs["options"] = func.__slash_options__

        command = ApplicationCommand(func, **kwargs)
        return command

    return inner

def user_command(**kwargs):
    def inner(func):
        kwargs["type"] = 2

        command = ApplicationCommand(func, **kwargs)
        return command

    return inner

def message_command(**kwargs):
    def inner(func):
        kwargs["type"] = 3

        command = ApplicationCommand(func, **kwargs)
        return command

    return inner