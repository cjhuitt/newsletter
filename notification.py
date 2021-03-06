#! /usr/bin/env python3

import argparse
from slackclient import SlackClient
import os
import time

token = "garbage"
try:
    token = os.environ['API_TOKEN']
except:
    pass

slack = SlackClient(token)

default_message = """:robot_face:I am a bot, posting on behalf of {0}. Beep-boop:robot_face:

We’re presently preparing to publish a newsletter for this slack, and
some of the content you authored or participated or were named in has
been selected for potential inclusion.  While all the content is
public in channel history, we’re attempting to make the collation
process opt-in.

The current draft is at {1}

We would like you to agree to the inclusion of your content.  Ideally,
you’d provide blanket inclusion approval, but if you’d like to have
finer control, or even blanket exclusion, that’s perfectly acceptable
as well.

*If you don’t specifically approve your mentions/content by {2}, we will exclude it*.

{0} will see your response to this message, which can be as
short as “Ok” (just this newsletter), “Ok - always”, “No”, and
“No - always” (or :thumbsup:/:thumbsdown:).  (They are also available
to reword how your contribution was presented if you feel it doesn't match
your intended message.)

If you have questions, please either reply here, or in #rands-newsletter if
they’re more general.

Thanks for being an active part of the community, and we look forward
to hearing from you soon.

:robot_face:Beep-boop. Bot out:robot_face:"""


class Options(argparse.ArgumentParser):
    """
    Consolidates our argument handling.
    """

    def __init__(self):
        super().__init__(description='Notify a set of users about their potential inclusion in a newsletter.')
        self.parsed_args = None
        self.usernames = []

        self.add_argument("--users", "--user", nargs='+', metavar="USER",
                          help="Notify the given user(s).  "
                               "Must provide users either on the command line or via file")
        self.add_argument("--user_list", metavar="FILE",
                          help="Notify the user(s) given in the file (one per line).  "
                               "Must provide users either on the command line or via file")
        self.add_argument("--url",
                          help="Use the given *public* url in the message.  "
                               "Must include either url/deadline OR a message file")
        self.add_argument("--deadline", metavar="DATE",
                          help="Use the given deadline for responses in the message (pass in quotes, as in "
                               "'Monday 9 AM Pacific').  "
                               "Must include either url/deadline OR a message file")
        self.add_argument("--message", metavar="FILE",
                          help="Use the given file's contents as the message to send.  "
                               "Must include either url/deadline OR a message file")
        self.add_argument("--dry", action="store_true",
                          help="Print the message and users, but don't actually send the messages")

    def store_args(self):
        self.parsed_args = self.parse_args()
        self._compile_lists()
        if not self.usernames:
            self.error("At least one user or file of users is required.")
        if not ((self.parsed_args.url and self.parsed_args.deadline) or self.parsed_args.message):
            self.error("Either URL and deadline or message file is required.")
        self._normalize_usernames()

    def _compile_lists(self):
        self._add_command_line_users()
        self._add_users_from_file()

    def _add_command_line_users(self):
        if self.parsed_args.users:
            self.usernames.extend(self.parsed_args.users)

    def _add_users_from_file(self):
        if self.parsed_args.user_list:
            with open(self.parsed_args.user_list, 'r') as f:
                for line in f:
                    self.usernames.append(line.rstrip('\n') )

    def _normalize_usernames(self):
        normalized = set()
        for user in self.usernames:
            if user[0] == '@':
                normalized.add(user[1:])
            else:
                normalized.add(user)
        self.usernames = sorted(normalized, key=lambda s: s.casefold())


class OriginatingUser:
    """
    Information about the originating user.
    """

    def __init__(self):
        response = slack.api_call("users.profile.get")
        if not response['ok']:
            print(response)
            raise RuntimeError
        profile = response['profile']
        self.username = "@" + profile['display_name_normalized']
        self.firstname = self.username
        if profile['first_name']:
            self.firstname = profile['first_name']


class User:
    """
    Tracks and aggregates information specific to a user.
    """

    def __init__(self, user_id, name):
        self.id = user_id
        self.name = name


class Message:
    """
    Handle formatting the message to be sent and sending it as appropriate
    """

    def __init__(self, message_file, url, deadline, from_user):
        self._message = default_message.format(from_user.firstname, url, deadline)
        if message_file:
            with open(message_file, 'r') as f:
                self._message = f.read()
        pass

    def send(self, from_user, users, dry=False):
        if dry:
            print("-" * 80)
            print(self._message)
            print("-" * 80)
            print("")

        for user in users:
            if not dry:
                print("Notifying @{}".format(user.name))
                response = slack.api_call("chat.postMessage", channel=user.id, text=self._message,
                                          as_user=from_user.username)
                if not response['ok']:
                    print(response)
                    raise RuntimeError
            else:
                print("Would have notified @{}".format(user.name))


def FetchUserIds(users):
    user_ids = []
    next = ''
    while True:
        response = slack.api_call("users.list", limit=250, cursor=next)
        if not response['ok']:
            if 'error' in response and 'ratelimited' in response['error']:
                print("pausing...")
                time.sleep(3)
                continue
            else:
                print(response)
                raise RuntimeError

        if 'members' in response:
            for member in response['members']:
                id = member['id']
                name = ''
                real_name = ''
                if 'name' in member:
                    name = member['name']
                if 'real_name' in member:
                    real_name = member['real_name']

                if name in users:
                    user_ids.append(User(id, name))
                    users.remove(name)
                elif real_name in users:
                    user_ids.append(User(id, real_name))
                    users.remove(real_name)

        if not users:
            return user_ids, users

        if not 'response_metadata' in response:
            return user_ids, users
        elif not 'next_cursor' in response['response_metadata']:
            return user_ids, users
        next = response['response_metadata']['next_cursor']
        if not next:
            return user_ids, users


if __name__ == '__main__':
    options = Options()
    options.store_args()

    from_user = OriginatingUser()
    (user_ids, unidentified_users) = FetchUserIds(options.usernames)

    message = Message(message_file=options.parsed_args.message, url=options.parsed_args.url,
                      deadline=options.parsed_args.deadline, from_user=from_user)
    message.send(from_user, user_ids, dry=options.parsed_args.dry)

    if unidentified_users:
        print()
        print("*** Unable to identify the following users ***")
        for user in unidentified_users:
            print("@{}".format(user))
