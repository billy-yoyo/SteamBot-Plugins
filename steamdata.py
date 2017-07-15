import time


class SteamData:
    def __init__(self):
        self.loaded = False

        self.cooldowns = {}
        self.save_cooldown = 30
        self.WATCHER_CAP = 20
        self.last_save = time.time()

        self.valid_commands = []

        self.cooldown_whitelist = ["141964149356888064", "125526751064489984", "228782404775575553"]

        self.commands_count = 0
        self.start_time = time.time()
        self.languages = {}

    def check_cooldown(self, userid, name, msg):
        ctime = time.time()
        if userid not in self.cooldown_whitelist and userid in self.cooldowns and name in self.cooldowns[userid] and ctime < self.cooldowns[userid][name]:
            remaining = int((self.cooldowns[userid][name] - ctime) * 100) / 100
            raise CooldownError(msg.replace("%t", str(remaining)).replace("%cd", str(self.cooldowns[name])))


class CooldownError(Exception):
    def __init__(self, message):
        super(CooldownError, self).__init__(message)


class BannedError(Exception):
    pass


class CommandPermissionError(Exception):
    pass
