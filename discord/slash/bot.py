from ..client import Client
from .command import (
    slash_command,
    user_command,
    message_command,
    resolve_message,
    resolve_user,
)
from ..http import Route

from collections import defaultdict

__all__ = ("Bot",)


class Bot(Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._to_register = []
        self._commands = {}

    def add_command(self, command):
        self._to_register.append(command)

    def slash_command(self, **kwargs):
        def inner(func):
            command = slash_command(**kwargs)(func)
            self.add_command(command)
            return command

        return inner

    def user_command(self, **kwargs):
        def inner(func):
            command = user_command(**kwargs)(func)
            self.add_command(command)
            return command

        return inner

    def message_command(self, **kwargs):
        def inner(func):
            command = message_command(**kwargs)(func)
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

            if data["type"] == 1:
                subcommand_name, options = await command.resolve_options(interaction)

                if subcommand_name is not None:
                    for option in command.options:
                        callback = option.subcommand_callback
                        break
                    else:
                        raise ValueError("unknown subcommand!")

                else:
                    callback = command.callback

                await callback(interaction, **options)
            elif data["type"] == 2:
                user = resolve_user(interaction, data["target_id"])
                await command.callback(interaction, user)
            elif data["type"] == 3:
                message = resolve_message(interaction, data["target_id"])
                await command.callback(interaction, message)

        elif interaction.type.value == 4:
            command = self._commands[data["id"]]
            if data["name"] != command.name:
                for option in command.options:
                    if option.name == data["name"]:
                        command = option
                        break
                else:
                    raise ValueError("unknown subcommand!")

            for selected_option in data["options"]:
                for option in command.options:
                    if selected_option["name"] == option.name:
                        choices = await option.autocomplete(
                            interaction, selected_option["value"]
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
