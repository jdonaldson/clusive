// There are TWO TTS systems used - Readium's built-in read-aloud functionality for the reader page,
// and the more basic clusiveTTS defined here for other pages.
//
/* eslint-disable no-use-before-define */
/* global D2Reader */

var clusiveTTS = {
    synth: window.speechSynthesis,
    elementsToRead: [],
    region: {},
    currentVoice: null,
    voiceRate: 1,
    textElement: null,
    copiedElement: null,
    autoScroll: true,
    userScrolled: false,
    readerReady: false,
    isPaused: false,
    utterance: null
};

// Bind controls
$(document).ready(function() {
    'use strict';

    // Allow play button to have toggle behavior
    $('.tts-play').on('click', function(e) {
        clusiveTTS.setRegion(e.currentTarget);

        if (clusiveTTS.region.mode === 'Readium') {
            console.debug('Readium read aloud play button clicked');
            if (!clusiveTTS.synth.speaking) {
                D2Reader.startReadAloud();
                clusiveTTS.updateUI('play');
            } else {
                D2Reader.stopReadAloud();
                clusiveTTS.updateUI('stop');
            }
        } else {
            console.debug('read aloud play button clicked');
            if (!clusiveTTS.synth.speaking) {
                clusiveTTS.resetState();
                clusiveTTS.read();
                clusiveTTS.updateUI('play');
            } else {
                clusiveTTS.stopReading();
                clusiveTTS.updateUI('stop');
            }
        }
    });

    $('.tts-stop').on('click', function(e) {
        clusiveTTS.setRegion(e.currentTarget);

        if (clusiveTTS.region.mode === 'Readium') {
            console.debug('Readium read aloud stop button clicked');
            D2Reader.stopReadAloud();
        } else {
            console.debug('read aloud stop button clicked');
            clusiveTTS.stopReading();
            // Call resetElements since some browsers do not always get the `utterance.onend` event
            clusiveTTS.resetElements();
        }
        clusiveTTS.updateUI('stop');
    });

    $('.tts-pause').on('click', function(e) {
        clusiveTTS.setRegion(e.currentTarget);

        if (clusiveTTS.region.mode === 'Readium') {
            console.debug('Readium read aloud pause button clicked');
            D2Reader.pauseReadAloud();
        } else {
            console.debug('read aloud pause button clicked');
            // Don't reset `userScrolled` here, otherwise page might jump due to async reading
            clusiveTTS.isPaused = true;
            clusiveTTS.synth.pause();
        }
        clusiveTTS.updateUI('pause');
    });

    $('.tts-resume').on('click', function(e) {
        clusiveTTS.setRegion(e.currentTarget);

        if (clusiveTTS.region.mode === 'Readium') {
            console.debug('Readium read aloud resume button clicked');
            D2Reader.resumeReadAloud();
        } else {
            console.debug('read aloud resume button clicked');
            clusiveTTS.userScrolled = false;

            // Resume by speaking utterance if one is queued
            if (clusiveTTS.utterance) {
                clusiveTTS.synth.speak(clusiveTTS.utterance);
                clusiveTTS.utterance = null;
            }
            clusiveTTS.synth.resume();
            clusiveTTS.isPaused = false;
        }
        clusiveTTS.updateUI('resume');
    });
});

window.addEventListener('unload', function() {
    'use strict';

    if (clusiveTTS.region.mode === 'Readium') {
        D2Reader.stopReadAloud();
    } else {
        clusiveTTS.stopReading();
    }
});

clusiveTTS.setRegion = function(ctl) {
    'use strict';

    var newRegion = {};
    newRegion.elm = ctl.closest('.tts-region');
    newRegion.mode = Object.prototype.hasOwnProperty.call(newRegion.elm.dataset, 'mode') ? newRegion.elm.dataset.mode : null;

    // Stop any previous region from reading
    if (Object.keys(clusiveTTS.region).length && (clusiveTTS.region.elm !== newRegion.elm)) {
        if (clusiveTTS.region.mode === 'Readium') {
            console.debug('Readium read aloud stop on region change');
            D2Reader.stopReadAloud();
        } else {
            console.debug('read aloud stop on region change');
            clusiveTTS.stopReading();
        }
        clusiveTTS.updateUI('stop');
    }

    if (clusiveTTS.region.elm !== newRegion.elm) {
        clusiveTTS.region = newRegion;
    }
};

clusiveTTS.updateUI = function(mode) {
    'use strict';

    if (!Object.keys(clusiveTTS.region).length) { return; }

    var region = clusiveTTS.region.elm;

    switch (mode) {
        case 'resume':
        case 'play': {
            region.classList.remove('paused');
            region.classList.add('active');
            break;
        }
        case 'pause': {
            region.classList.add('paused');
            region.classList.add('active');
            break;
        }
        default: {
            region.classList.remove('paused');
            region.classList.remove('active');
        }
    }
};

// Stop an in-process reading
clusiveTTS.stopReading = function(reset) {
    'use strict';

    if (typeof reset === 'undefined') { reset = true; }
    clusiveTTS.elementsToRead = [];
    if (reset) {
        clusiveTTS.scrollWatchStop();
    }
    clusiveTTS.synth.cancel();
    clusiveTTS.resetState();
    clusiveTTS.updateUI();
};

clusiveTTS.scrollWatch = function(event) {
    'use strict';

    if (event instanceof KeyboardEvent) {
        switch (event.key) {
            case 'ArrowUp':
            case 'ArrowDown': {
                clusiveTTS.userScrolled = true;
                break;
            }
            default:
                break;
        }
    } else {
        clusiveTTS.userScrolled = true;
    }
};

clusiveTTS.scrollWatchStart = function() {
    'use strict';

    clusiveTTS.userScrolled = false;
    $(document).on('wheel keydown touchmove', clusiveTTS.scrollWatch);
};

clusiveTTS.scrollWatchStop = function() {
    'use strict';

    clusiveTTS.userScrolled = false;
    $(document).off('wheel keydown touchmove', clusiveTTS.scrollWatch);
};

clusiveTTS.isVisible = function(elem) {
    'use strict';

    return Boolean(elem.offsetWidth || elem.offsetHeight
        || elem.getClientRects().length && window.getComputedStyle(elem).visibility !== 'hidden');
};

clusiveTTS.readQueuedElements = function() {
    'use strict';

    var toRead = null;

    while (clusiveTTS.elementsToRead.length && toRead === null) {
        toRead = clusiveTTS.elementsToRead.shift();
        if (!clusiveTTS.isVisible(toRead.element)) {
            toRead = null;
        }
    }

    if (typeof toRead !== 'undefined' && toRead !== null) {
        var end = toRead.end ? toRead.end : null;
        clusiveTTS.readElement(toRead.element, toRead.offset, end);
    } else {
        console.debug('Done reading elements');
        clusiveTTS.updateUI('stop');
    }
};

clusiveTTS.readElement = function(textElement, offset, end) {
    'use strict';

    var synth = clusiveTTS.synth;
    clusiveTTS.textElement = $(textElement);
    var elementText = clusiveTTS.textElement.text();
    var contentText = end ? elementText.slice(offset, end) : elementText.slice(offset);

    // Preserve and hide the original element so we can handle the highlighting in an
    // element without markup
    // TODO: this needs improved implementation longer term
    clusiveTTS.copiedElement = clusiveTTS.textElement.clone(false);
    clusiveTTS.textElement.after(clusiveTTS.copiedElement);
    clusiveTTS.textElement.hide();

    var utterance = clusiveTTS.makeUtterance(contentText);

    utterance.onboundary = function(e) {
        var preceding = '';
        var middle = '';
        var following = '';

        if (e.name === 'sentence') {
            console.debug('sentence boundary', e.charIndex, e.charLength, contentText.slice(e.charIndex, e.charIndex + e.charLength));
        }
        if (e.name === 'word') {
            console.debug('word boundary', e.charIndex, e.charLength, contentText.slice(e.charIndex, e.charIndex + e.charLength));

            // iOS/Safari does not report charLength
            if (typeof e.charLength !== 'undefined') {
                preceding = elementText.substring(0, offset + e.charIndex);
                middle = elementText.substring(offset + e.charIndex, offset + e.charIndex + e.charLength);
                following = elementText.substring(offset + e.charIndex + e.charLength);
            } else {
                // Find first word boundary after index
                var subString = e.charIndex ? elementText.substring(offset + e.charIndex) : elementText;
                var boundaryMatch = subString.match(/\s\b\S?/);
                var boundaryIndex = boundaryMatch ? boundaryMatch.index : 0;
                var textLength = subString.length;

                boundaryIndex = textLength < boundaryIndex ? textLength : boundaryIndex;

                preceding = elementText.substring(0, offset + e.charIndex);
                // middle = elementText.substring(offset + e.charIndex, offset + e.charIndex + boundaryIndex);
                following = elementText.substring(offset + e.charIndex + boundaryIndex);

                if (!boundaryMatch) {
                    middle = elementText.substring(offset + e.charIndex);
                    following = '';
                } else {
                    middle = elementText.substring(offset + e.charIndex, offset + e.charIndex + boundaryIndex);
                }
            }
        }

        var newText = preceding + '<span class="tts-currentWord">' + middle + '</span>' + following;
        clusiveTTS.copiedElement.html(newText);

        // Keep current word being read in view
        if (clusiveTTS.autoScroll && !clusiveTTS.userScrolled) {
            // TODO: Investigate why can't hook into copiedElement
            // var wordCurr = clusiveTTS.copiedElement.querySelector('.tts-currentWord');
            var wordCurr = document.querySelector('.tts-currentWord');
            if (wordCurr) {
                wordCurr.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });
            }
        }
    };

    utterance.onend = function() {
        console.debug('utterance ended');
        clusiveTTS.resetElements();
    };

    if (!clusiveTTS.isPaused) {
        synth.speak(utterance);
    } else {
        clusiveTTS.utterance = utterance;
    }
};

clusiveTTS.resetState = function() {
    'use strict';

    clusiveTTS.utterance = null;
    clusiveTTS.isPaused = false;
};

clusiveTTS.resetElements = function() {
    'use strict';

    console.debug('read aloud reset elements');
    clusiveTTS.copiedElement.remove();
    clusiveTTS.textElement.show();
    clusiveTTS.readQueuedElements();
};

clusiveTTS.makeUtterance = function(text) {
    'use strict';

    if (typeof SpeechSynthesisUtterance === 'function') {
        var utt = new SpeechSynthesisUtterance(text);
        if (clusiveTTS.currentVoice) {
            utt.voice = clusiveTTS.currentVoice;
        }
        if (clusiveTTS.voiceRate) {
            utt.rate = clusiveTTS.voiceRate;
        }
        return utt;
    }
    console.warn('Speech synthesis unsupported by this browser');
    return null;
};

clusiveTTS.readElements = function(textElements) {
    'use strict';

    // Cancel any active reading
    clusiveTTS.stopReading(false);

    $.each(textElements, function(i, e) {
        clusiveTTS.elementsToRead.push(e);
    });

    clusiveTTS.readQueuedElements();
};

clusiveTTS.getAllTextElements = function(documentBody) {
    'use strict';

    var textElements = documentBody.find('h1, h2, h3, h4, h5, h6, p');
    return textElements;
};

clusiveTTS.getReaderIFrameBody = function() {
    'use strict';

    var readerIframe = $('#D2Reader-Container').find('iframe');
    return readerIframe.contents().find('body');
};

clusiveTTS.getReaderIframeSelection = function() {
    'use strict';

    return $('#D2Reader-Container').find('iframe')[0].contentWindow.getSelection();
};

clusiveTTS.filterReaderTextElementsBySelection = function(textElements, userSelection) {
    'use strict';

    var filteredElements = textElements.filter(function(i, elem) {
        return userSelection.containsNode(elem, true);
    });
    return filteredElements;
};

clusiveTTS.isSelection = function(selection) {
    'use strict';

    return !(selection.type === 'None' || selection.type === 'Caret');
};

clusiveTTS.read = function() {
    'use strict';

    var isReader = $('#D2Reader-Container').length > 0;
    var elementsToRead;
    var isSelection;
    var selection;

    if (isReader) {
        elementsToRead = clusiveTTS.getAllTextElements(clusiveTTS.getReaderIFrameBody());
        selection = clusiveTTS.getReaderIframeSelection();
    } else {
        elementsToRead = clusiveTTS.getAllTextElements($('body'));
        selection = window.getSelection();
    }

    isSelection = clusiveTTS.isSelection(selection);

    clusiveTTS.scrollWatchStart();
    if (isSelection) {
        clusiveTTS.readSelection(elementsToRead, selection);
    } else {
        clusiveTTS.readAll(elementsToRead);
    }
};

clusiveTTS.readAll = function(elements) {
    'use strict';

    var toRead = [];
    $.each(elements, function(i, elem) {
        var elementToRead = {
            element: elem,
            offset: 0
        };
        toRead.push(elementToRead);
    });

    clusiveTTS.readElements(toRead);
};

// TODO: this needs refactoring to (among other things) extract the Selection-related functions
// for general usage
clusiveTTS.readSelection = function(elements, selection) {
    'use strict';

    var filteredElements = clusiveTTS.filterReaderTextElementsBySelection(elements, selection);
    var selectionDirection = clusiveSelection.getSelectionDirection(selection, selectionTexts);
    var firstNodeOffSet;

    if (selectionDirection === clusiveSelection.directions.FORWARD) {
        firstNodeOffSet = selection.anchorOffset;
    } else if (selectionDirection === clusiveSelection.directions.BACKWARD) {
        firstNodeOffSet = selection.focusOffset;
    }

    var selectionTexts = clusiveSelection.getSelectionTextAsArray(selection);

    // Check the selectionTexts against the filteredElements text, eliminate
    // selectionTexts that don't appear in the element text (ALT text, hidden text elements, etc)

    selectionTexts = selectionTexts.filter(function(selectionText) {
        var trimmed = selectionText.trim();
        var found = false;
        $.each(filteredElements, function(i, elem) {
            var elemText = $(elem).text();
            if (elemText.includes(trimmed)) {
                found = true;
            }
        });
        return found;
    });

    var toRead = [];
    $.each(filteredElements, function(i, elem) {
        var fromIndex = i === 0 ? firstNodeOffSet : 0;
        var selText = selectionTexts[i].trim();

        var textOffset = $(elem).text().indexOf(selText, fromIndex);

        var textEnd = selText.length;

        console.debug('textOffset/textEnd', textOffset, textEnd);

        var elementToRead = {
            element: elem,
            offset: textOffset,
            end: textOffset + textEnd
        };
        toRead.push(elementToRead);
    });
    // TODO: how to preserve ranges, while not selecting the substituted ones?
    selection.removeAllRanges();
    clusiveTTS.readElements(toRead);
};

// Return all voices known to the system for the given language.
// Language argument can be of the form "en" or "en-GB".
// If system default voice is on this list, it will be listed first.
clusiveTTS.getVoicesForLanguage = function(language) {
    'use strict';

    var voices = [];
    window.speechSynthesis.getVoices().forEach(function(voice) {
        if (voice.lang.startsWith(language)) {
            if (voice.default) {
                voices.unshift(voice); // Put system default voice at the beginning of the list
            } else {
                voices.push(voice);
            }
        }
    });
    return voices;
};

clusiveTTS.setCurrentVoice = function(name) {
    'use strict';

    // Eventually we may be able to switch voices mid-utterance, but for now have to stop speech
    clusiveTTS.stopReading();
    if (name) {
        window.speechSynthesis.getVoices().forEach(function(voice) {
            if (voice.name === name) {
                clusiveTTS.currentVoice = voice;
                if (clusiveTTS.readerReady) {
                    var voiceSpecs = {
                        usePublication: true,
                        lang: voice.lang,
                        name: voice.name
                    };
                    console.debug('setting D2Reader voice to ', voiceSpecs);
                    D2Reader.applyTTSSettings({
                        voice: voiceSpecs
                    });
                }
            }
        });
    } else {
        clusiveTTS.currentVoice = null;
        if (clusiveTTS.readerReady) {
            console.debug('Unsetting D2Reader voice');
            D2Reader.applyTTSSettings({
                voice: null
            });
        }
    }
};

clusiveTTS.readAloudSample = function() {
    'use strict';

    var utt = clusiveTTS.makeUtterance('Testing, testing, 1 2 3');
    window.speechSynthesis.speak(utt);
};

var clusiveSelection = {
    directions: {
        FORWARD: 'Forward',
        BACKWARD: 'Backward',
        UNCERTAIN: 'Uncertain'
    }
};

clusiveSelection.getSelectionDirection = function(selection) {
    'use strict';

    var selectionDirection;
    var selectionTexts = clusiveSelection.getSelectionTextAsArray(selection);

    var anchorNode = selection.anchorNode;
    var selectedAnchorText = selection.anchorNode.textContent.slice(selection.anchorOffset);

    var focusNode = selection.focusNode;
    var selectedFocusText = selection.focusNode.textContent.slice(selection.focusOffset);

    // Selection within a single element, direction can be determined by comparing anchor and focus offset
    if (anchorNode.textContent === focusNode.textContent) {
        selectionDirection = selection.anchorOffset < selection.focusOffset ? clusiveSelection.directions.FORWARD : clusiveSelection.directions.BACKWARD;
    // The first block of selection text is matched in the anchor element; forward selection
    } else if (selectedAnchorText === selectionTexts[0].trim()) {
        selectionDirection = clusiveSelection.directions.FORWARD;
    // The first block of selection text is matched in the focus element; backward selection
    } else if (selectedFocusText === selectionTexts[0].trim()) {
        selectionDirection = clusiveSelection.directions.BACKWARD;
    // This should eventually be eliminated as other scenarios get covered
    // TODO: check for anchorText / focusText within larger elements - might be divided by inline tags, etc
    } else { selectionDirection = clusiveSelection.directions.UNCERTAIN; }

    return selectionDirection;
};

// Get the selection text as an array, splitting by the newline character
clusiveSelection.getSelectionTextAsArray = function(selection) {
    'use strict';

    return selection.toString().split('\n').filter(function(text) {
        return text.length > 1;
    });
};
