import asyncio
import multiprocessing as mp
import re

from pyrogram import filters

from wbb import app
from wbb.utils.filter_groups import regex_group

__MODULE__ = "Sed"
__HELP__ = "**Usage:**\ns/foo/bar"

DELIMITERS = ("/", ":", "|", "_")
REGEX_TIMEOUT_SECONDS = 5


def _regex_sub_worker(
    pattern: str,
    replacement: str,
    source_text: str,
    ignore_case: bool,
    replace_all: bool,
    result_queue,
):
    flags = re.I if ignore_case else 0
    count = 0 if replace_all else 1

    try:
        result = re.sub(pattern, replacement, source_text, count=count, flags=flags)
        result_queue.put(("ok", result))
    except re.error:
        result_queue.put(("regex_error", ""))


def run_regex_with_timeout(
    pattern: str,
    replacement: str,
    source_text: str,
    ignore_case: bool,
    replace_all: bool,
) -> str:
    result_queue = mp.Queue(maxsize=1)
    process = mp.Process(
        target=_regex_sub_worker,
        args=(
            pattern,
            replacement,
            source_text,
            ignore_case,
            replace_all,
            result_queue,
        ),
    )
    process.start()
    process.join(REGEX_TIMEOUT_SECONDS)

    if process.is_alive():
        process.terminate()
        process.join()
        raise asyncio.TimeoutError

    if result_queue.empty():
        return ""

    status, result = result_queue.get()
    if status == "regex_error":
        raise re.error("invalid regex")

    return result


@app.on_message(
    filters.regex(r"s([{}]).*?\1.*".format("".join(DELIMITERS))),
    group=regex_group,
)
async def sed(_, message):
    if not message.text:
        return

    text_content = str(message.text)
    sed_result = separate_sed(text_content)

    if message.reply_to_message:
        if message.reply_to_message.text:
            to_fix = message.reply_to_message.text
        elif message.reply_to_message.caption:
            to_fix = message.reply_to_message.caption
        else:
            return
        if not sed_result:
            return
        repl, repl_with, flags = sed_result

        if not repl:
            return await message.reply_text(
                "You're trying to replace... nothing with something?"
            )

        try:
            if infinite_checker(repl):
                return await message.reply_text("Nice try -_-")

            text = await asyncio.to_thread(
                run_regex_with_timeout,
                repl,
                repl_with,
                to_fix,
                "i" in flags,
                "g" in flags,
            )
            text = text.strip()
        except asyncio.TimeoutError:
            return await message.reply_text("Regex took too long to compute.")
        except re.error:
            return

        # empty string errors -_-
        if len(text) >= 4096:
            await message.reply_text(
                "The result of the sed command was too long for \
                                                 telegram!"
            )
        elif text:
            await message.reply_to_message.reply_text(text)


def infinite_checker(repl):
    regex = [
        r"\((.{1,}[\+\*]){1,}\)[\+\*].",
        r"[\(\[].{1,}\{\d(,)?\}[\)\]]\{\d(,)?\}",
        r"\(.{1,}\)\{.{1,}(,)?\}\(.*\)(\+|\* |\{.*\})",
    ]
    for match in regex:
        if re.search(match, repl):
            return True
    return False


def separate_sed(sed_string):
    if not isinstance(sed_string, str):
        sed_string = str(sed_string)

    if (
        len(sed_string) >= 3
        and sed_string[1] in DELIMITERS
        and sed_string.count(sed_string[1]) >= 2
    ):
        delim = sed_string[1]
        start = counter = 2
        while counter < len(sed_string):
            if sed_string[counter] == "\\":
                counter += 1

            elif sed_string[counter] == delim:
                replace = sed_string[start:counter]
                counter += 1
                start = counter
                break

            counter += 1

        else:
            return None
        while counter < len(sed_string):
            if (
                sed_string[counter] == "\\"
                and counter + 1 < len(sed_string)
                and sed_string[counter + 1] == delim
            ):
                sed_string = sed_string[:counter] + sed_string[counter + 1 :]

            elif sed_string[counter] == delim:
                replace_with = sed_string[start:counter]
                counter += 1
                break

            counter += 1
        else:
            return replace, sed_string[start:], ""

        flags = ""
        if counter < len(sed_string):
            flags = sed_string[counter:]
        return replace, replace_with, flags.lower()
