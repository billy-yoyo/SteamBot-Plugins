

"""
Context object:

    Variable Attributes:

        message         - discord.Message object
        channel         - discord.Channel object
        formatting      - string, the formatting for the current command
        lang            - Language object
        marked          - whether the command was marked (e.g. steam game* instead of steam game)
        steamsearch     - the aiosteamsearch module
        sredis          - the steam redis collection module for accessing the database (RedisCollection object)
        sdata           - hub for per-session steambot data (SteamData object)
        client          - the steam client
        marked          - whether or not the command was marked (steam game vs steam *game)


    Function Attributes:

        format(message, include_head=True)      - sets the formatting, this is already called for the plugin
        get_prefix(default)                     - returns the prefix for this context, or the given default if none found
        set_prefix(prefix, server_prefix=True)  - sets the prefix for this context
        get_all_permissions(key)                - get the required permissions for a given command
        check_permissions(key)                  - check if the user for this context has permission to use that command
        is_premium()                            - returns true or false depending on if the user for this context is premium
        say(message, dest=None)                 - sends a "safe" message to this context, coroutine
        typing(dest=None)                       - just client.send_typing(dest or ctx.channel)



Language object:

    Function Attributes:

        get(base, name, join=True)     - gets a key from a specific category, join determines if the result should be joined
        get_cooldown(name, join=True)  - gets a cooldown message under "name"
        get_message(name, join=True)   - gets a message under "name"
        get_error(name, join=True)     - gets an error under "name"
        get_exception(name, join=True) - gets an exception under "name"



SteamData object:

    Variable Attributes:

        loaded                  - whether or not the bot is loaded (should always be true, no need to check)
        cooldowns               - the cooldowns for each command (dict)
        save_cooldown           - the cooldown for quite a few things the bot does on loop
        WATCHER_CAP             - the cap on the number of watchers each user can have
        last_save               - the time of the last "save" (the bot does quite a few things during this save)
        valid_commands          - list of all registered commands
        cooldown_whitelist      - list of users exempt from cooldowns
        commands_count          - meant to be the number of commands used in this session (unreliable)
        start_time              - the time the bot started
        languages               - a dict containing all the languages


    Function Attributes:

        check_cooldown(userid, name, msg) - checks if that user is on cooldown, name is the name of the command



RedisCollection object:

    Variable Attributes:

        redis_server    - the root redis server all the helpers connect to
        client          - the discord client
        steamsearch     - the aiosteamsearch instance
        sdata           - hub for per-session steambot data (SteamData object)

        watcher         - contains helper functions for the watcher db (WatcherRedis object)
        premium         - contains helper functions for the premium db (PremiumRedis object)
        billboard       - contains helper functions for the billboard db (BillboardRedis object)
        permissions     - contains helper functions for the permissions db (PermissionRedis object)
        languages       - contains helper functions for the languages db (LanguageRedis object)
        currency        - contains helper functions for the currency db (CurrencyRedis object)
        country         - contains helper functions for the country db (CountryRedis object)
        names           - contains helper functions for the names db (NameRedis object)
        marked          - contains helper functions for the marked db (MarkedRedis object)
        banned          - contains helper functions for the banned db (BannedRedis object)
        recommendations - contains helper functions for the recommendations db (RecommendationRedis object)
        query           - contains helper functions for the query db (QueryRedis object)
        shard_tracker   - contains helper functions for the shard_tracker db (ShardTrackerRedis object)

"""


class SteamBotPlugin:
    def __init__(self, func, cooldown, name, format, pass_name, cd_name):
        self.func = func
        self.cooldown = cooldown
        self.format = format
        self.name = name
        self.pass_name = pass_name
        self.cd_name = cd_name or name
        self.checks = []

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)


class InvalidPlugin(Exception):
    pass


def plugin(format, cooldown, name=None, pass_name=False, cd_name=None):
    """Decorator for creating a plugin, the decorated function takes arguments:
    func(ctx, client, args) where:
        ctx is a Context object,
        client is a discord.Client object,
        args is the arguments for the command, e.g. for "steam game rocket league" it would be ["rocket", "league"]

    :param format: formatting for the command, e.g. "steam game [game]"
    :param cooldown: the cooldown for the command, e.g. 30
    :param name: the name of the command (defaults to function name, cannot contain spaces
    """
    if name is not None and " " in name:
        raise InvalidPlugin("Name cannot contain spaces")

    def decorator(func):
        pluginname = name
        if name is None:
            pluginname = func.__name__
        return SteamBotPlugin(func, cooldown, pluginname, format, pass_name, cd_name)

    return decorator


def permission(permission_name, for_channel=True):
    permission_name = permission_name.lower().strip().replace(" ", "_").replace("__", "_")

    def decorator(plugin):
        if isinstance(plugin, SteamBotPlugin):
            if for_channel:
                plugin.checks.append(lambda ctx, args: getattr(ctx.channel.permissions_for(ctx.message.author), permission_name, False))
            else:
                plugin.checks.append(lambda ctx, args: getattr(ctx.message.author.server_permissions, permission_name, False))
            return plugin
        else:
            raise InvalidPlugin("Permission decorator must be applied above plugin")

    return decorator


def check(func):
    def decorator(plugin):
        if isinstance(plugin, SteamBotPlugin):
            plugin.checks.append(func)
            return plugin
        else:
            raise InvalidPlugin("Check decorator must be applied above plugin")

    return decorator

"""
Example:

@check(lambda ctx, args: "billy" in ctx.message.author.name)
@permission("manage messages")
@plugin("steam mycmd [a] [b]", 10)
@asyncio.coroutine
def mycmd(ctx, a, b):
    yield from ctx.typing()

    result = int(a) + int(b)
    yield from ctx.say("Result is: %s" % result)

Just import this module, create all your functions, save the file and send it to me.
I'll check it over and add it to the bot :)
"""