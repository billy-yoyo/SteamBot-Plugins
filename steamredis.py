import redis
import discord
import asyncio
import time
import os
import json
import traceback
from steamdata import BannedError, CommandPermissionError


class LanguageError(Exception):
    pass


class Language:
    @staticmethod
    def load_language(name, backup=None):
        if os.path.exists("languages/" + name + ".json"):
            with open("languages/" + name + ".json", "rb") as f:
                return Language(name, json.loads(f.read().decode("utf-8")), backup=backup)
        return None

    def __init__(self, collection, name, dct, backup=None):
        self.collection = collection
        self.name = name
        self.handler = RedisHandler("languageshub::" + name, collection.redis_server)
        self.backup = backup
        self.update_server(dct)

    def update_server(self, dct):
        for section in dct:
            for item in dct[section]:
                if isinstance(dct[section][item], list) or isinstance(dct[section][item], tuple):
                    self.handler[section + "::" + item + "::length"] = len(dct[section][item])
                    for i in range(len(dct[section][item])):
                        self.handler[section + "::" + item + "::" + str(i)] = dct[section][item][i]
                else:
                    self.handler[section + "::" + item] = dct[section][item]

    def get(self, base, name, join=True):
        key = base + "::" + name
        if key + "::length" in self.handler:
            length = int(self.handler[key + "::length"].decode("utf-8"))
            result = [""] * length
            for i in range(length):
                result[i] = self.handler[key + "::" + str(i)].decode("utf-8")
            if join:
                return "\n".join(result)
            return result
        elif key in self.handler:
            return self.handler[key].decode("utf-8")
        elif self.backup is not None:
            return self.backup.get(base, name, join=join)
        else:
            raise LanguageError("failed to resolve language key " + base + "/" + name)

    #def get(self, base, name, join=True):
    #    if base in self.raw and name in self.raw[base]:
    #        result = self.raw[base][name]
    #        if isinstance(result, list) and join:
    #            return "\n".join(result)
    #        return result
    #    else:
    #        raise LanguageError

    def get_cooldown(self, name, join=True):
        return self.get("cooldowns", name, join=join)

    def get_message(self, name, join=True):
        return self.get("messages", name, join=join)

    def get_error(self, name, join=True):
        return "~" + self.get("errors", name, join=join)

    def get_exception(self, name, join=True):
        return self.get("exceptions", name, join)


class RedisHandler:
    def __init__(self, name, redis):
        self.name = name
        self.redis = redis

    def __setitem__(self, key, value):
        self.redis.set(self.name + "::" + key, value)

    def __getitem__(self, item):
        return self.redis.get(self.name + "::" + item)

    def __contains__(self, item):
        return self.redis.exists(self.name + "::" + item)

    def __delitem__(self, key):
        self.redis.delete(self.name + "::" + key)


class RedisCollection:
    def __init__(self, client, steamsearch, sdata):
        self.redis_server = redis.StrictRedis(host="localhost", port=6379, db=0)
        self.client = client
        self.steamsearch = steamsearch
        self.sdata = sdata

        self.watcher = WatcherRedis(self)
        self.premium = PremiumRedis(self)
        self.billboard = BillboardRedis(self)
        self.permissions = PermissionRedis(self)
        self.languages = LanguageRedis(self)
        self.currency = CurrencyRedis(self)
        self.country = CountryRedis(self)
        self.names = NameRedis(self)
        self.marked = MarkedRedis(self)
        self.banned = BannedRedis(self)
        self.recommendations = RecommendationRedis(self)
        self.query = QueryRedis(self)
        self.shard_tracker = ShardTrackerRedis(self)


class WatcherRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("watcher", collection.redis_server)
        self.collection = collection

    def get_old(self):
        if "old" in self.handler:
            raw_old = self.handler["old"].decode("utf-8")
            return {a[0]: float(a[1]) for a in [x.split(",") for x in raw_old.split(":") if x != ""]}
        return {}

    def set_old(self, old):
        self.handler["old"] = ":".join(str(x) + "," + str(y) for (x, y) in old.items())

    def get_watcher_game_name(self, gameid):
        if "gamename::" + str(gameid) in self.handler:
            return self.handler["gamename::" + str(gameid)].decode("utf-8")
        return str(gameid)

    def get_watchers(self):
        if "watchers" in self.handler:
            raw_watchers = self.handler["watchers"].decode("utf-8")
            return [x.split(",") for x in raw_watchers.split(":") if x != ""]
        return []

    def get_watcher_id(self, user):
        watcherid = 0
        if "watcherid" in self.handler:
            watcherid = int(self.handler["watcherid"].decode("utf-8"))

        if "watcherid::" + str(user) in self.handler:
            return int(self.handler["watcherid::" + str(user)].decode("utf-8")), watcherid
        return 0, watcherid

    def add_watcher(self, userid, locationid, locationtype, percent, gameid, gamename=None):
        watcher_number, watcherid = self.get_watcher_id(userid)
        if watcher_number >= self.collection.sdata.WATCHER_CAP:
            return -1

        watchers = self.get_watchers()
        if any(x[0] == userid and x[2] == locationid and x[-1] == gameid for x in watchers):
            return -2
        watcher = (userid, watcherid, locationid, locationtype, percent, gameid)
        print("new watcher: %s" % str(watcher))
        watchers.append(watcher)
        new_watchers = ":".join(",".join(str(x) for x in watcher) for watcher in watchers)
        self.handler["watchers"] = new_watchers

        self.handler["watcherid::" + str(userid)] = str(watcher_number + 1)
        self.handler["watcherid"] = str(watcherid + 1)

        if gamename is not None:
            self.handler["gamename::" + gameid] = gamename
        return watcherid

    def remove_watcher(self, userid, watcherid):

        watchers = self.get_watchers()
        new_watchers = [watcher for watcher in watchers if not (watcher[0] == userid and watcher[1] == watcherid)]
        if len(watchers) == len(new_watchers):
            return False

        self.handler["watchers"] = ":".join(",".join(str(x) for x in watcher) for watcher in new_watchers)
        return True

    @asyncio.coroutine
    def check_watchers(self, optional_test=None):
        if optional_test is None:
            optional_test = {}
        old = self.get_old()
        print("old: %s" % old)
        result_pack = yield from self.collection.steamsearch.check_game_sales([
                                                                     (watcher[-1], watcher[-2], self.collection.country.get_country(watcher[0]),
                                                                      watcher[0], watcher[1], watcher[2], watcher[3])
                                                                     for watcher in self.get_watchers()
                                                                     ], old, optional_test)
        results, new_old = result_pack

        game_names = {}
        #  result: gameid, check_percent, old_percent, price_overview, name, userid, watcherid, locationid, locationtype
        for result in results:
            gameid, check_percent, old_percent, price_overview, name, userid, watcherid, locationid, locationtype = result
            print("price overview: %s" % price_overview)
            new_percent = price_overview["discount_percent"]
            if gameid not in game_names:
                game_names[gameid] = self.get_watcher_game_name(gameid)
            game_name = game_names[gameid]
            lang = self.collection.language.get_language(userid)
            if new_percent > old_percent:
                if old_percent == 0:
                    line = lang.get_message("deal_started") % (game_name, str(new_percent) + "%")
                else:
                    line = lang.get_message("deal_increased") % (
                    game_name, str(old_percent) + "%", str(new_percent) + "%")
            elif new_percent >= check_percent:
                line = lang.get_message("deal_reduced") % (game_name, str(old_percent) + "%", str(new_percent) + "%")
            else:
                line = lang.get_message("deal_ended") % (game_name, str(old_percent))

            line = "[" + str(watcherid) + "]:  " + line
            if locationtype == "mention":
                line += "  <@" + userid + ">"

            if locationtype == "pm":
                destination = discord.utils.get(self.collection.client.get_all_members(), id=locationid)
                if destination is None:
                    destination = yield from self.collection.client.get_user_info(locationid)
            else:
                destination = discord.Object(locationid)

            yield from self.collection.client.send_message(destination, line)
        print("new old: %s" % new_old)
        self.set_old(new_old)


class PremiumRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("premium", collection.redis_server)
        self.collection = collection # type: RedisCollection

    def get_premium_users(self):
        if "users" in self.handler:
            return self.handler["users"].decode("utf-8").split(",")
        return []

    def add_premium_users(self, users):
        users += self.get_premium_users()
        self.handler["users"] = ",".join(users)

    def set_premium_users(self, users):
        self.handler["users"] = ",".join(users)

    def update_premium_users(self, server):
        premium_roles = ["209743495064322049", "220107636878737409", "254044942962393088",
                         "229660520842526730", "229663214332411904"]
        premium_members = [member.id for member in server.members if
                           any(role.id in premium_roles for role in member.roles)]
        self.set_premium_users(premium_members)
        return premium_members


class BillboardRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("billboard", collection.redis_server)
        self.collection = collection

    def get_billboard_curators(self):
        if "curators" in self.handler:
            return self.handler["curators"].decode("utf-8").split(",")
        return []

    def set_billboard_curators(self, curators):
        self.handler["curators"] = ",".join(curators)

    def remove_billboard_curators(self, users):
        if not isinstance(users, list) and not isinstance(users, tuple): users = [users]
        curators = self.get_billboard_curators()
        for user in users:
            if user in curators: curators.remove(user)
        self.set_billboard_curators(curators)

    def add_billboard_curators(self, user):
        curators = self.get_billboard_curators()
        if user not in curators: curators.append(user)
        self.set_billboard_curators(curators)

    def get_billboard_posts(self):
        if "posts" in self.handler:
            posts = [x.split("=") for x in self.handler["posts"].decode("utf-8").split(";")]
            return {x: y for x, y in posts}
        return {}

    def set_billboard_posts(self, posts):
        posts = ";".join("%s=%s" % (x, y) for x, y in posts.items())
        self.handler["posts"] = posts

    def add_billboard_post(self, post, msgids):
        posts = self.get_billboard_posts()
        posts[post] = msgids
        self.set_billboard_posts(posts)

    def remove_billboard_post(self, post):
        posts = self.get_billboard_posts()
        if post in posts:
            del posts[post]
        self.set_billboard_posts(posts)

    def get_billboard_channels(self):
        if "channels" in self.handler:
            return self.handler["channels"].decode("utf-8").split(",")
        return []

    def set_billboard_channels(self, channels):
        self.handler["channels"] = ",".join(channels)

    def add_billboard_channel(self, channel):
        channels = self.get_billboard_channels()
        if channel not in channels: channels.append(channel)
        self.set_billboard_channels(channels)

    def get_billboard_postid(self):
        if "postid" in self.handler:
            return int(self.handler["postid"].decode("utf-8"))
        return 0

    def set_billboard_postid(self, postid):
        self.handler["postid"] = str(postid)

    def remove_billboard_channel(self, channel):
        channels = self.get_billboard_channels()
        if channel in channels: channels.remove(channel)
        self.set_billboard_channels(channels)


class PermissionRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("permissions", collection.redis_server)
        self.collection = collection

    def get_permissions(self, key, id, server=True):
        dbkey = key + "::" + ("server" if server else "channel") + "::" + id
        if dbkey + "::length" in self.handler:
            length = int(self.handler[dbkey + "::length"].decode("utf-8"))
            return [self.handler[dbkey + "::" + str(i)].decode("utf-8") for i in range(length)]
        return []

    def add_permissions(self, key, permissions, id, server=True):
        dbkey = key + "::" + ("server" if server else "channel") + "::" + id
        length = 0
        if dbkey + "::length" in self.handler:
            length = int(self.handler[dbkey + "::length"].decode("utf-8"))
            self.handler[dbkey + "::length"] = str(length + len(permissions))
        for i, permission in enumerate(permissions):
            self.handler[dbkey + "::" + str(length + i)] = permission

    def clear_permissions(self, key, id, server=True):
        dbkey = key + "::" + ("server" if server else "channel") + "::" + id
        self.handler[dbkey + "::length"] = "0"

    def remove_permissions(self, key, permissions, id, server=True):
        dbkey = key + "::" + ("server" if server else "channel") + "::" + id
        perms = self.get_permissions(key, id, server)
        j = 0
        removed = []
        for perm in perms:
            if perm not in permissions:
                self.handler[dbkey + "::" + str(j)] = perm
                j += 1
            else:
                removed.append(perm)
        self.handler[dbkey + "::length"] = str(j)
        return removed


class LanguageRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("languages", collection.redis_server)
        self.collection = collection

    def load_language(self, name, backup=None):
        language = Language.load_language(name, backup=backup)
        self.collection.sdata.languages[name] = language
        return language

    def load_all_languages(self):
        onlyfiles = [f for f in os.listdir("languages/") if os.path.isfile(os.path.join("languages/", f))]
        loaded = []
        english = self.load_language("english")
        loaded.append(english)
        for filename in onlyfiles:
            if not filename.startswith("english"):
                if filename.endswith(".json"):
                    lang = filename[:-5]
                    self.load_language(lang, backup=english)
                    loaded.append(lang)
        print("loaded languages: " + str(loaded))

    def get_language(self, userid, serverid=None):
        if userid in self.handler:
            return self.collection.sdata.languages[self.handler[userid].decode("utf-8")]
        elif serverid is not None and "server::" + serverid in self.handler:
            return self.collection.sdata.languages[self.handler["server::" + serverid].decode("utf-8")]
        else:
            return self.collection.sdata.languages["english"]

    def set_language(self, id, language, server=False):
        if isinstance(language, Language):
            language = language.name
        if server:
            self.handler["server::" + id] = language
        else:
            self.handler[id] = language


class CurrencyRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("currencies", collection.redis_server)
        self.collection = collection

    def get_currency(self, userid):
        if userid in self.handler:
            return (self.handler["code::" + userid].decode("utf-8"), self.handler["symbol::" + userid].decode("utf-8"))
        else:
            return "GBP", "£"

    def set_currency(self, userid, code, symbol):
        self.handler["code::" + userid] = code
        self.handler["symbol::" + userid] = symbol


class CountryRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("countries", collection.redis_server)
        self.collection = collection

    def get_country(self, userid):
        if userid in self.handler:
            return self.handler[userid].decode("utf-8")
        else:
            return "gb"


class NameRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("names", collection.redis_server)
        self.collection = collection

    def get_name(self, userid):
        if userid in self.handler:
            return self.handler[userid].decode("utf-8")
        else:
            return "unknown"

    def get_saved_name(self, ctx, term, marked):
        if term == "" and ctx.message.author.id in self.handler:
            return self.handler[ctx.message.author.id].decode("utf-8"), self.collection.marked.get_saved_mark(ctx.message.author.id, marked)
        elif len(ctx.message.mentions) == 1 and ctx.message.mentions[0].id in self.handler:
            return self.handler[ctx.message.mentions[0].id].decode("utf-8"), self.collection.marked.get_saved_mark(ctx.message.mentions[0].id,
                                                                                           marked)
        else:
            return term, marked


class MarkedRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("marks", collection.redis_server)
        self.collection = collection

    def get_saved_mark(self, key, marked):
        if key in self.handler and self.handler[key].decode("utf-8").lower() != "none":
            return True
        return marked


class BannedRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("global_bans", collection.redis_server)
        self.collection = collection

    def is_banned(self, category, id, key):
        rediskey = category + "::" + id
        # print("checking key %s" % )
        if rediskey in self.handler:
            keys = self.handler[rediskey].decode("utf-8").split(";")
            # print("found keys %s under %s" % (keys, rediskey))
            return key in keys or "*" in keys
        return False

    def check_ban(self, ctx, msg, key):
        #if key in self.collection.sdata.valid_commands:
        #    add_stats(commands=1)
        if False and msg.author.id == "141964149356888064":
            return
        elif self.is_banned("user", msg.author.id, key) or self.is_banned("channel", msg.channel.id, key) or \
                (msg.server is not None and self.is_banned("server", msg.server.id, key)):
            raise BannedError
        elif not ctx.check_permissions(key):
            raise CommandPermissionError


class RecommendationRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("recommendations", collection.redis_server)
        self.collection = collection

    @asyncio.coroutine
    def get_recommendations(self, appid, timeout=10):
        if "appid" in self.handler:
            appids = self.handler["appid"].decode("utf-8").split(",")
            last_time = int(appids[0])
            if time.time() - last_time < 1800:
                return appids[1:]

        recommendations = yield from self.collection.steamsearch.get_recommendations(appid, timeout=timeout)
        if len(recommendations) > 0:
            self.handler["appid"] = str(int(time.time())) + "," + ",".join(recommendations)
            return recommendations
        return None

    @asyncio.coroutine
    def get_recommendations_multi(self, appids, limit=-1, timeout=10, resolve=False):
        results = {}
        failed = []
        for app_name in appids:
            if resolve:
                appid, title = yield from self.collection.steamsearc.get_app(app_name)
            else:
                appid = app_name
            print("resolved %s" % appid)
            if appid is not None:
                similar = yield from self.get_recommendations(appid, timeout=timeout)
                if similar is not None:
                    print("found similar: %s" % similar)
                    for similar_id in similar:
                        if similar_id in results:
                            results[similar_id] += 1
                        else:
                            results[similar_id] = 1
                else:
                    failed.append(app_name)
        print(results)
        final = sorted(results, key=lambda x: results[x], reverse=True)
        if limit > 0:
            final = final[:limit]
        return final, failed

    @asyncio.coroutine
    def find_recommendations(self, app_names, limit=-1, timeout=10):
        results, failed = yield from self.get_recommendations_multi(app_names, limit=limit, timeout=timeout, resolve=True)
        print(results)
        new_results = []
        for result in results:
            name = yield from self.collection.steamsearc.get_game_name_by_id(result)
            new_results.append(name)
        return new_results, failed


class QueryRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("queries", collection.redis_server)
        self.collection = collection

    def query_in_progress(self):
        if "in_progress" in self.handler:
            return self.handler["in_progress"].decode("utf-8") == "true"
        return False

    def check_responded(self):
        if "response_%s" % self.collection.client.my_shard_id in self.handler:
            return self.handler["response_%s" % self.collection.client.my_shard_id].decode("utf-8") != ""
        return True

    def start_query(self, query):
        if "in_progress" not in self.handler:
            self.handler["in_progress"] = str(True)
        else:
            raw_progress = self.handler["in_progress"].decode("utf-8")
            # print("RAW IN_PROGRESS: %s | BOOL IN_PROGRESS: %s" % (raw_progress, to_bool(raw_progress)))

            if raw_progress == "true":
                return False

            self.handler["in_progress"] = str(True)
        self.handler["query"] = query

        for shard in range(self.collection.client.my_shard_count):
            if shard != self.collection.client.my_shard_id:
                self.handler["response_%s" % shard] = ""

        self.respond_to_query(query)
        return True

    def respond_to_query(self, query=None):
        if query is None:
            query = self.handler["query"].decode("utf-8")
        try:
            response = str(eval(query))
            if response == "": response = "-- EMPTY --"
        except:
            if query is not None:
                response = traceback.format_exc()
            else:
                response = "ERROR"
        self.handler["response_%s" % self.collection.client.my_shard_id] = response

    def check_completed(self):
        if not self.query_in_progress(): return False
        for shard in range(self.collection.client.my_shard_count):
            if self.handler["response_%s" % shard].decode("utf-8") == "": return False
        return True

    @asyncio.coroutine
    def wait_for_query(self):
        while True:
            if self.check_completed():
                self.handler["in_progress"] = str(False)
                self.handler["query"] = ""
                return
            asyncio.sleep(0.5)


class ShardTrackerRedis:
    def __init__(self, collection):
        self.handler = RedisHandler("shardtrackers", collection.redis_server)
        self.collection = collection


