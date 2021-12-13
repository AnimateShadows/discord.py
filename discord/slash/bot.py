from ..client import Client
from .command import slash_command, user_command, message_command

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
            resp = await self.http.bulk_upsert_global_commands(application_id, [c.to_dict() for c in global_commands])

            for r in resp:
                for c in global_commands:
                    if c.name == r["name"]:
                        self._commands[r["id"]] = c

        for guild in guild_commands:
            resp = await self.http.bulk_upsert_guild_commands(application_id, guild, [c.to_dict() for c in guild_commands[guild]])

            for r in resp:
                for c in guild_commands[guild]:
                    if c.name == r["name"]:
                        self._commands[r["id"]] = c