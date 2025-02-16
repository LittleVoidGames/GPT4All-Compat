# GPT4All-Compat
GPT4All Streaming Compatibility Layer

This is a personal project I started to attempt to make a compatibility layer for programs like Cline to be able to use GPT4All, despite GPT4All not having streaming support. There are some know issues with it, including how it occasionally removes the white space at that start of new chunks when it stitches them back together. For now, I'm a bit tired of tinkering with it, so I'm releasing it as MIT licensed. 


# To Use

- Run this script in a terminal.
- Start GPT4ALL
- Make sure GPT4All is set to use the same port (default 4891) as the script. Change either if needed.
- Point your external program (like Cline) at the port created by this script instead of the port GPT4All is using. (default 8086)
- Profit?

Please submit a PR if you have any fixes you're like to contribute back upsteam. I kind of gave on fixing the whitespace issue, so if you're just looking for something to tinker with, that's a good place to start. 

Thank you to Nomic for working on a great LLM interfact that works with my old AMD GPU!
