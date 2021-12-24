from ..client import Client
from .command import (
    slash_command as _slash_command,
    user_command as _user_command,
    message_command as _message_command,
    resolve_message,
    resolve_user,
)
from ..http import Route

from collections import defaultdict
from importlib import import_module

__all__ = ("Bot",)


class Bot(Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._to_register = []
        self._commands = {}
    
    def load_extension(self, path):
        module = import_module(path)
        module.setup(self)
        # expected to add cogs here...

    def add_cog(self, cog):
        for command in cog.__slash_commands__:
            self.add_command(command, cog=cog)

    def add_command(self, command, cog=None):
        if cog is not None:
            setattr(command, "cog", cog)
        else:
            setattr(command, "cog", None)

        self._to_register.append(command)

    def slash_command(self, **kwargs):
        def inner(func):
            command = _slash_command(**kwargs)(func)
            self.add_command(command)
            return command

        return inner

    def user_command(self, **kwargs):
        def inner(func):
            command = _user_command(**kwargs)(func)
            self.add_command(command)
            return command

        return inner

    def message_command(self, **kwargs):
        def inner(func):
            command = _message_command(**kwargs)(func)
            self.add_command(command)
            return command

        return inner

    async def start(self, token):
        await self.login(token)

        await self.register_commands()
        await self.connect(reconnect=True)

    async def register_commands(self):
        global_commands = []
        guild_commands = defaultdict(list)

        application_id = (await self.application_info()).id

        for command in self._to_register:
            if command.guild_id is not None:
                guild_commands[command.guild_id].append(command)
            else:
                global_commands.append(command)

        if global_commands:
            resp = await self.http.bulk_upsert_global_commands(
                application_id, [c.to_dict() for c in global_commands]
            )

            permissions = []

            for r in resp:
                for c in global_commands:
                    if c.name == r["name"]:
                        self._commands[r["id"]] = c

                        if c.permissions is not None:
                            permissions.append({"id": r["id"], "permissions": [p.to_dict() for p in c.permissions]})

            if permissions:
                r = Route(
                    "PUT",
                    "/applications/{application_id}/commands/permissions",
                    application_id=application_id,
                )
                await self.http.request(r, json=permissions)

        for guild in guild_commands:
            resp = await self.http.bulk_upsert_guild_commands(
                application_id, guild, [c.to_dict() for c in guild_commands[guild]]
            )

            permissions = []

            for r in resp:
                for c in guild_commands[guild]:
                    if c.name == r["name"]:
                        self._commands[r["id"]] = c

                        if c.permissions is not None:
                            permissions.append({"id": r["id"], "permissions": [p.to_dict() for p in c.permissions]})

            if permissions:
                r = Route(
                    "PUT",
                    "/applications/{application_id}/guilds/{guild_id}/commands/permissions",
                    application_id=application_id,
                    guild_id=guild,
                )
                await self.http.request(r, json=permissions)

    async def on_interaction(self, interaction):
        data = interaction.data

        if interaction.type.value == 2:
            command = self._commands[data["id"]]
            if command.cog is not None:
                args = (command.cog, interaction)
            else:
                args = (interaction,)

            if data["type"] == 1:
                subcommand_name, options = await command.resolve_options(interaction)

                if subcommand_name is not None:
                    for option in command.options:
                        if option.name == subcommand_name:
                            callback = option.subcommand_callback
                            break
                    else:
                        raise ValueError("unknown subcommand!")

                else:
                    callback = command.callback

                await callback(*args, **options)
            elif data["type"] == 2:
                user = resolve_user(interaction, data["target_id"])
                await command.callback(*args, user)
            elif data["type"] == 3:
                message = resolve_message(interaction, data["target_id"])
                await command.callback(*args, message)

        elif interaction.type.value == 4:
            command = self._commands[data["id"]]
            cog = command.cog

            if data["options"][0]["type"] == 1:
                for option in command.options:
                    if option.name == data["options"][0]["name"]:
                        command = option
                        options = data["options"][0]["options"]
                        break
                else:
                    raise ValueError("unknown subcommand!")
            else:
                options = data["options"]

            for selected_option in options:
                for option in command.options:
                    if selected_option["name"] == option.name:

                        try:
                            choices = await option.autocomplete(
                                interaction, selected_option["value"]
                            )
                        except TypeError:
                            # might be in a cog!?
                            
                            choices = await option.autocomplete(
                                cog, interaction, selected_option["value"]
                            )

                        choices = [{"name": c, "value": c} for c in choices]

                        r = Route(
                            "POST",
                            "/interactions/{interaction_id}/{interaction_token}/callback",
                            interaction_id=interaction.id,
                            interaction_token=interaction.token,
                        )
                        data = {"type": 8, "data": {"choices": choices}}

                        await self.http.request(r, json=data)
