#!/bin/bash

if [ ! -d "locale" ]; then
    mkdir locale
    if [ ! -d "locale/ru" ]; then
        mkdir locale/ru
        mkdir locale/ru/LC_MESSAGES
    fi
    if [ ! -d "locale/en" ]; then
        mkdir locale/en
        mkdir locale/en/LC_MESSAGES
    fi
fi

xgettext --language=Python --keyword=_t --output=locale/wayback_fetcher.pot wayback_fetcher.py

if [ -f "locale/ru/LC_MESSAGES/wayback_fetcher.po" ]; then
    for lang in ru en; do
        msgmerge --update --backup=none locale/$lang/LC_MESSAGES/wayback_fetcher.po locale/wayback_fetcher.pot
        msgfmt --check locale/$lang/LC_MESSAGES/wayback_fetcher.po -o locale/$lang/LC_MESSAGES/wayback_fetcher.mo
    done
else
    for lang in ru en; do
        msginit --locale=$lang --input=locale/wayback_fetcher.pot --output-file=locale/$lang/LC_MESSAGES/wayback_fetcher.po --no-translator
    done
fi
