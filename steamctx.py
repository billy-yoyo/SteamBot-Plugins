from steamredis import RedisHandler
import asyncio
import discord
import time


class Context:
    def __init__(self, client, steamsearch, sdata, sredis):
        self.client = client
        self.message = None
        self.channel = None
        self.formatting = ""
        self.steamsearch = steamsearch
        self.sredis = sredis # type: steamredis.RedisCollection
        self.sdata = sdata
        self.marked = False

        self._prefix_handler = RedisHandler("prefixes", sredis.redis_server)

        self.cd_name = ""
        self.cd_userid = ""

    def set(self, message):
        self.message = message
        self.channel = message.channel
        self.formatting = ""

        return self

    def format(self, message, include_head=True):
        if include_head:
            message = "Invalid usage: `" + message + "`"
        self.formatting = message

    def get_prefix(self, default):
        if isinstance(self.channel, discord.Channel) and "channel::" + self.channel.id in self._prefix_handler:
            return self._prefix_handler["channel::" + self.channel.id].decode("utf-8")
        elif self.message.server is not None and "server::" + self.message.server.id in self._prefix_handler:
            return self._prefix_handler["server::" + self.message.server.id].decode("utf-8")
        else:
            return default

    def set_prefix(self, prefix, server_prefix=True):
        if server_prefix:
            if prefix == "" or prefix == "steam ":
                del self._prefix_handler["server::" + self.message.server.id]
            else:
                self._prefix_handler["server::" + self.message.server.id] = prefix
        else:
            if prefix == "" or prefix == "steam ":
                del self._prefix_handler["channel::" + self.channel.id]
            else:
                self._prefix_handler["channel::" + self.channel.id] = prefix

    def get_all_permissions(self, key):
        return self.sredis.permissions.get_permissions(key, self.channel.server.id, True) + get_permissions(key, self.channel.id, False)

    def check_permissions(self, key):
        perms = self.get_all_permissions(key)
        user_perms = self.channel.permissions_for(self.message.author)
        for perm in perms:
            print(perm)
            if perm.startswith("role|"):
                roleid = perm[5:]
                if not any(role.id == roleid for role in self.message.author.roles):
                    return False
            elif getattr(user_perms, perm, True) is False:
                return False
        return True

    def is_premium(self):
        return self.message.author.id in self.sredis.premium.get_premium_users()

    def cooldown(self, userid, name):
        self.cd_name = name
        self.cd_userid = userid
        ctime = time.time()
        if userid not in self.sdata.cooldowns:
            self.sdata.cooldowns[userid] = {}
        if name in self.sdata.cooldowns:
            self.sdata.cooldowns[userid][name] = ctime + self.sdata.cooldowns[name]

    def reset_cooldown(self):
        if self.cd_userid in self.sdata.cooldowns and self.cd_name in self.sdata.cooldowns[self.cd_userid]:
            del self.sdata.cooldowns[self.cd_userid][self.cd_name]

    @property
    def lang(self):
        return self.sredis.languages.get_language(self.message.author.id, self.message.server.id)

    @asyncio.coroutine
    def say(self, message, dest=None):
        if dest is None:
            dest = self.channel

        if message.replace("`", "").strip().startswith("~¬"):
            message = message.replace("~¬", "", 1)
        elif message.replace("`", "").strip().startswith("~"):
            message = message.replace("~", "", 1).replace("http", "http".join(u'\u200b'))

        result = yield from self.client.send_message(dest, u'\u200b' + message.replace("@", "@" + u'\u200b'))
        return result

    @asyncio.coroutine
    def typing(self, dest=None):
        if dest is None:
            dest = self.channel

        yield from self.client.send_typing(dest)