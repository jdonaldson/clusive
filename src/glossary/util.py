import json
import logging
import os

from lemminflect import getAllLemmas, getAllInflections

from wordnet import util as wordnetutil
from .bookglossary import BookGlossary

logger = logging.getLogger(__name__)

# Note, currently lookup depends directly on Wordnet.
# Eventually, the goal is to have multiple possible backends and a way to
# configure which one(s) to use.

book_glossaries = {}


def has_definition(book, word):
    """Determine whether the given word exists in the book's glossary or dictionary.
     We don't want to query or cue words when we don't have a definition."""
    return lookup(book, word) is not None


def lookup(book, word):
    defs = None
    if book:
        # First try to find in a book glossary
        book_id = book.id
        if not book_glossaries.get(book_id):
            book_glossaries[book_id] = BookGlossary(book_id)
        defs = book_glossaries[book_id].lookup(word)
        if (defs):
            defs['source'] = 'Book'
    if not defs:
        # Next try Wordnet
        defs = wordnetutil.lookup(word)
        if (defs):
            defs['source'] = 'Wordnet'
    return defs


def base_form(word, return_word_if_not_found=True):
    """
    Return the base form of the given word.
    In the case where the word can be seen as different parts of speech with different base forms,
    this returns the shortest. If they are the same length, it chooses the alphabetically first one.
    For example, "outing" is base form of noun, but also the inflected form of the verb "out", so
    this method will return "out".

    If word is not found in Wordnet, will normally return the given word unchanged.
    But if return_word_if_not_found is set to False, returns None instead.
    :param word:
    :return: base form
    """
    wl = word.lower()
    all_forms = set()
    for pos, lemmas in getAllLemmas(wl).items():
        # getAllLemmas can return multiple possible baseforms for each POS, eg british and american versions.
        # The first listed form is supposed to be the most common so that is the only one we consider.
        all_forms.add(lemmas[0])
    if all_forms:
        return min(all_forms, key=base_form_sort_key)
    else:
        if return_word_if_not_found:
            return wl
        return None


def base_form_sort_key(word):
    # We sort by length primarily, so that the shortest potential base form will be returned.
    # Within length, sort alphabetically. Needed so that return value is deterministic even with multiple,
    # same-length base forms possible  (eg "more" -> "more" or "much")
    return "%03d%s" % (len(word), word)


def all_forms(word):
    wl = word.lower()
    all_forms = set()
    all_forms.add(wl)
    for list in getAllInflections(wl).values():
        all_forms.update(list)
    return all_forms


def test_glossary_file(glossfile):
    """
    Sanity check the given glossary JSON file.

    Returns an error as a string, or None if the file looks good.
    Should be rewritten to continue checking and return ALL errors.
    """
    if not os.path.exists(glossfile):
        return 'File doesn\'t exist'
    book_dir = os.path.dirname(glossfile)
    with open(glossfile, 'r', encoding='utf-8') as file:
        try:
            glossary = json.load(file)
        except:
            return "JSON Decode error in %s" % (glossfile)
        for entry in glossary:
            if not 'headword' in entry:
                return "In %s, missing headword in %s" % (glossfile, entry)
            # assert entry['headword'] == base_form(entry['headword']) or entry['headword']=='install', \
            #             "In %s, glossary word %s is not base form, should be %s" \
            #             % (glossfile, entry['headword'], base_form(entry['headword']))
            if entry['headword'] != base_form(entry['headword']):
                logger.info("Non baseform in %s: %s (should be %s)",
                            glossfile, entry['headword'], base_form(entry['headword']))
            if not 'alternateForms' in entry:
                return "In %s, %s missing alternateForms" % (glossfile, entry['headword'])
            if not 'meanings' in entry:
                return "In %s, %s missing meanings" % (glossfile, entry['headword'])
            for m in entry['meanings']:
                if not 'pos' in m:
                    return "In %s word %s, missing pos in %s" % (glossfile, entry['headword'], m)
                if not 'definition' in m:
                    return "In %s word %s, missing definition in %s" % (glossfile, entry['headword'], m)
                if not 'examples' in m:
                    return "In %s word %s, missing examples in %s" % (glossfile, entry['headword'], m)
                if 'images' in m:
                    for i in m['images']:
                        if not 'src' in i:
                            return "In %s word %s, missing src for image" % (glossfile, entry['headword'])
                        if not os.path.exists(os.path.join(book_dir, i['src'])):
                            return "In %s word %s, image doesn't exist: %s" % (glossfile, entry['headword'], os.path.join(book_dir, i['src']))
                        if not 'alt' in i:
                            return "In %s word %s, missing alt for image" % (glossfile, entry['headword'])
                        if not 'description' in i:
                            return "In %s word %s, missing description for image" % (glossfile, entry['headword'])
                        # optional for now
                        # assert 'caption' in i, "In %s word %s, missing caption for image" % (glossfile, entry['headword'])
                        # assert 'source' in i, "In %s word %s, missing source for image" % (glossfile, entry['headword'])
    return None
