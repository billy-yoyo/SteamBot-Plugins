from steambotplugin import plugin, permission, check
import asyncio
import discord


@plugin("steam game [game]", 10)
@asyncio.coroutine
def game(ctx, *spl):
    ctx.sdata.check_cooldown(ctx.message.author.id, "game", ctx.lang.get_cooldown("game"))
    ctx.format("steam game [game]")
    ctx.cooldown(ctx.message.author.id, "game")
    yield from ctx.client.send_typing(ctx.message.channel)
    term = " ".join(spl[2:])
    result = None
    if ctx.marked:
        term = term.lower().replace("-", " ").replace(":", "")
        if ctx.steamsearch.is_integer(term):
            result = yield from ctx.steamsearch.get_game_by_id(term, cc=ctx.sredis.country.get_country(ctx.message.author.id))
            if result is not None and result.title == "???":
                result = None
        else:
            results = yield from ctx.steamsearch.get_games(term, limit=20, cc=ctx.sredis.country.get_country(ctx.message.author.id))
            result = None
            for game in results:
                if game.title.lower().replace("-", " ").replace(":", "") == term:
                    result = game
                    break
    else:
        results = yield from ctx.steamsearch.get_games(term, limit=1, cc=ctx.sredis.country.get_country(ctx.message.author.id))
        if len(results) > 0:
            result = results[0]

    if result is not None:
        if result.discount == "":
            priceText = result.price
        else:
            priceText = result.discountPrice + " (" + result.discount + ", " + ctx.lang.get_message(
                "price") + " " + result.price + ")"

        if ctx.message.channel.permissions_for(ctx.message.server.me).embed_links:
            embed = discord.Embed()
            embed.description = "Results for game %s" % result.title
            embed.url = "http://www.steambot.site/commands/"
            # result.set_image_size(320, 120)
            embed.set_thumbnail(url=result.image)

            embed.set_author(name="SteamBot", icon_url=ctx.client.user.avatar_url)
            text = ctx.lang.get_message("game", join=False)
            line_contents = [
                (result.title,), (result.link,), (result.released,),
                (result.review, result.reviewLong), (priceText,),
            ]
            for i, line in enumerate(text):
                spl = line.split(":")
                title = spl[0].strip()
                content = ":".join(spl[1:]).strip()
                embed.add_field(name="**%s**" % title, value=content % line_contents[i])
            # embed.add_field(name="", value=ctx.lang.get_message("game") % (result.title, result.link, result.released, result.review, result.reviewLong, priceText))

            yield from ctx.client.send_message(ctx.channel, embed=embed)
        else:
            yield from ctx.say(("```prolog\n" + ctx.lang.get_message("game") + "\n```") % (
            result.title, result.link, result.released, result.review, result.reviewLong, priceText))
    else:
        yield from ctx.say(ctx.lang.get_error("game") % term)