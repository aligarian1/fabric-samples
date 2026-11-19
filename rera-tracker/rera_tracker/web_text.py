"""Words for the website and its emails, in English and Hindi.

Keep the wording factual.  The Hindi text was written by the developer, not a
translator: have a Hindi speaker read it before the site goes public.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# Bump this when the privacy notice changes; it is stored with each person's consent.
PRIVACY_VERSION = "2026-11-v1"

_TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        "site": "RERA Tracker",
        "tagline": "Your flat's RERA record, in plain language",
        "nav_home": "Home",
        "nav_privacy": "Privacy",
        "lang_switch": "हिन्दी",
        "indep": "Independent service. Not run by, or connected to, HRERA, the Government of Haryana or any builder. Information only, not legal advice.",
        "home_h": "Follow your flat's RERA record",
        "home_p": "Every day we read the public Haryana RERA pages and email you, in plain English or Hindi, when something changes: a new quarterly report, a new hearing, a change in the registration date, or a report that has not been filed.",
        "search_label": "Find your project",
        "search_ph": "Project name, builder or RERA ID",
        "search_btn": "Search",
        "covers": "Covers {n} projects registered with HRERA Gurugram and HRERA Panchkula. Records last read on {date}.",
        "covers_nodate": "Covers {n} projects registered with HRERA Gurugram and HRERA Panchkula.",
        "results_h": "Results for \"{q}\"",
        "results_none": "No project matched. Try a shorter part of the name.",
        "results_short": "Type at least 2 characters.",
        "results_more": "Showing the first {n} matches. Try a more specific search.",
        "valid_to": "valid to {date}",
        "lapsed_tag": "listed as lapsed",
        "asof": "Official record read on {date}.",
        "asof_list": "Project list read on {date}. The project page and quarterly reports are added once someone follows this project.",
        "official": "Official HRERA page",
        "alerts_h": "Get an email when something changes",
        "email": "Email address",
        "language": "Language of the emails",
        "consent": "I agree that {business} may use my email address to send me alerts about this project. I can stop at any time with the link in every email.",
        "privacy_link": "Privacy notice",
        "submit": "Send me a confirmation email",
        "form_note": "We will email you a link to confirm. Nothing is sent until you confirm.",
        "err_email": "Please enter a valid email address.",
        "err_consent": "Please tick the box to agree.",
        "err_form": "The form timed out or was sent too quickly. Please try again.",
        "err_mail": "We could not send the confirmation email right now. Please try again later.",
        "err_limit": "Too many requests. Please try again later.",
        "sent_h": "Check your email",
        "sent_p": "If that address can receive email, we have sent a link to confirm your alerts. The link works for {days} days. If you do not confirm, nothing is sent and we delete the request.",
        "confirm_h": "Confirm your alerts",
        "confirm_p": "Confirm that you want email alerts about {project}.",
        "confirm_btn": "Yes, send me alerts",
        "confirmed_h": "Alerts are on",
        "confirmed_p": "You will get your first status report with the next daily update, and after that an email only when something changes. Every email has a link to stop.",
        "link_bad_h": "This link does not work",
        "link_bad_p": "It may be incomplete or it may have expired. Please start again from the project page.",
        "unsub_h": "Stop alerts",
        "unsub_p": "Choose what to stop.",
        "unsub_project": "Stop alerts for {project}",
        "unsub_all": "Stop all alerts and delete my data",
        "unsub_done_project": "Alerts for {project} have stopped.",
        "unsub_done_all": "All alerts have stopped and your data has been deleted.",
        "unsub_nothing": "Nothing left to stop. We hold no data about you.",
        "notfound_h": "Page not found",
        "notfound_p": "We could not find that page.",
        "error_h": "Something went wrong",
        "error_p": "Please try again later.",
        "home_link": "Back to home",
        "privacy_h": "Privacy notice",
        "mail_confirm_subject": "Confirm your alerts for {project}",
        "mail_confirm_body": (
            "Hello,\n\nSomeone asked for email alerts about {project} ({builder}) on {site}. "
            "If that was you, confirm here:\n\n{url}\n\n"
            "The link works for {days} days. If it was not you, ignore this email: nothing will be sent "
            "and we will delete the request.\n\n{business}"
        ),
    },
    "hi": {
        "site": "RERA ट्रैकर",
        "tagline": "आपके फ़्लैट का RERA रिकॉर्ड, सरल भाषा में",
        "nav_home": "होम",
        "nav_privacy": "गोपनीयता",
        "lang_switch": "English",
        "indep": "यह एक स्वतंत्र सेवा है। इसे HRERA, हरियाणा सरकार या किसी बिल्डर ने नहीं चलाया है और न ही इनसे इसका कोई संबंध है। यह केवल जानकारी है, कानूनी सलाह नहीं।",
        "home_h": "अपने फ़्लैट का RERA रिकॉर्ड फ़ॉलो करें",
        "home_p": "हम हर दिन हरियाणा RERA के सार्वजनिक पेज पढ़ते हैं और कुछ बदलने पर आपको सरल अंग्रेज़ी या हिंदी में ईमेल भेजते हैं: नई तिमाही रिपोर्ट, नई सुनवाई, रजिस्ट्रेशन की तारीख में बदलाव, या दाखिल न की गई रिपोर्ट।",
        "search_label": "अपना प्रोजेक्ट खोजें",
        "search_ph": "प्रोजेक्ट का नाम, बिल्डर या RERA आईडी",
        "search_btn": "खोजें",
        "covers": "HRERA गुरुग्राम और HRERA पंचकूला में रजिस्टर्ड {n} प्रोजेक्ट शामिल हैं। रिकॉर्ड आखिरी बार {date} को पढ़े गए।",
        "covers_nodate": "HRERA गुरुग्राम और HRERA पंचकूला में रजिस्टर्ड {n} प्रोजेक्ट शामिल हैं।",
        "results_h": "\"{q}\" के नतीजे",
        "results_none": "कोई प्रोजेक्ट नहीं मिला। नाम का छोटा हिस्सा आज़माएँ।",
        "results_short": "कम से कम 2 अक्षर लिखें।",
        "results_more": "पहले {n} नतीजे दिखाए जा रहे हैं। थोड़ी सटीक खोज आज़माएँ।",
        "valid_to": "{date} तक वैध",
        "lapsed_tag": "लैप्स्ड के रूप में दर्ज",
        "asof": "आधिकारिक रिकॉर्ड {date} को पढ़ा गया।",
        "asof_list": "प्रोजेक्ट सूची {date} को पढ़ी गई। प्रोजेक्ट पेज और तिमाही रिपोर्ट तब जुड़ती हैं जब कोई इस प्रोजेक्ट को फ़ॉलो करता है।",
        "official": "HRERA का आधिकारिक पेज",
        "alerts_h": "कुछ बदलने पर ईमेल पाएँ",
        "email": "ईमेल पता",
        "language": "ईमेल की भाषा",
        "consent": "मैं सहमत हूँ कि {business} इस प्रोजेक्ट के अलर्ट भेजने के लिए मेरा ईमेल पता इस्तेमाल कर सकता है। मैं हर ईमेल में दिए लिंक से कभी भी रोक सकता/सकती हूँ।",
        "privacy_link": "गोपनीयता सूचना",
        "submit": "मुझे पुष्टि का ईमेल भेजें",
        "form_note": "हम पुष्टि के लिए एक लिंक ईमेल करेंगे। पुष्टि करने तक कुछ नहीं भेजा जाएगा।",
        "err_email": "कृपया सही ईमेल पता लिखें।",
        "err_consent": "सहमति के लिए बॉक्स पर निशान लगाएँ।",
        "err_form": "फ़ॉर्म का समय निकल गया या वह बहुत जल्दी भेजा गया। कृपया फिर कोशिश करें।",
        "err_mail": "अभी हम पुष्टि का ईमेल नहीं भेज पाए। कृपया बाद में फिर कोशिश करें।",
        "err_limit": "बहुत ज़्यादा अनुरोध। कृपया बाद में फिर कोशिश करें।",
        "sent_h": "अपना ईमेल देखें",
        "sent_p": "अगर वह पता ईमेल पा सकता है, तो हमने आपके अलर्ट की पुष्टि के लिए एक लिंक भेजा है। लिंक {days} दिन तक चलता है। पुष्टि न करने पर कुछ नहीं भेजा जाएगा और हम अनुरोध मिटा देंगे।",
        "confirm_h": "अलर्ट की पुष्टि करें",
        "confirm_p": "पुष्टि करें कि आप {project} के ईमेल अलर्ट चाहते हैं।",
        "confirm_btn": "हाँ, मुझे अलर्ट भेजें",
        "confirmed_h": "अलर्ट चालू हैं",
        "confirmed_p": "अगले रोज़ाना अपडेट के साथ आपको पहली स्थिति रिपोर्ट मिलेगी, उसके बाद कुछ बदलने पर ही ईमेल आएगा। हर ईमेल में रोकने का लिंक होगा।",
        "link_bad_h": "यह लिंक काम नहीं कर रहा",
        "link_bad_p": "हो सकता है वह अधूरा हो या उसकी अवधि खत्म हो गई हो। कृपया प्रोजेक्ट पेज से दोबारा शुरू करें।",
        "unsub_h": "अलर्ट रोकें",
        "unsub_p": "चुनें कि क्या रोकना है।",
        "unsub_project": "{project} के अलर्ट रोकें",
        "unsub_all": "सभी अलर्ट रोकें और मेरा डेटा मिटाएँ",
        "unsub_done_project": "{project} के अलर्ट बंद हो गए हैं।",
        "unsub_done_all": "सभी अलर्ट बंद हो गए हैं और आपका डेटा मिटा दिया गया है।",
        "unsub_nothing": "रोकने के लिए कुछ बचा नहीं है। हमारे पास आपका कोई डेटा नहीं है।",
        "notfound_h": "पेज नहीं मिला",
        "notfound_p": "हमें वह पेज नहीं मिला।",
        "error_h": "कुछ गड़बड़ हो गई",
        "error_p": "कृपया बाद में फिर कोशिश करें।",
        "home_link": "होम पर वापस जाएँ",
        "privacy_h": "गोपनीयता सूचना",
        "mail_confirm_subject": "{project} के अलर्ट की पुष्टि करें",
        "mail_confirm_body": (
            "नमस्ते,\n\n{site} पर किसी ने {project} ({builder}) के ईमेल अलर्ट माँगे हैं। "
            "अगर वह आप थे, तो यहाँ पुष्टि करें:\n\n{url}\n\n"
            "लिंक {days} दिन तक चलता है। अगर आप नहीं थे, तो इस ईमेल को अनदेखा करें: "
            "कुछ नहीं भेजा जाएगा और हम अनुरोध मिटा देंगे।\n\n{business}"
        ),
    },
}

_PRIVACY: Dict[str, List[Tuple[str, str]]] = {
    "en": [
        ("Who we are", "{business} runs this website. Contact: {contact}."),
        (
            "What we collect",
            "Your email address, the language you chose, the project you want alerts about, and the date and time you agreed. "
            "We do not ask for your name or phone number.",
        ),
        (
            "Why",
            "Only to confirm your address and to email you alerts about the project you chose. "
            "We do not use it for advertising and we do not sell it.",
        ),
        (
            "Where the project information comes from",
            "Public records on the Haryana RERA website (haryanarera.gov.in). We repeat what the records show, as filed by builders. "
            "It is information, not legal advice, and we are not connected to HRERA.",
        ),
        (
            "Who handles it",
            "The companies that host this website and send our email handle your email address on our behalf, only to run this service.",
        ),
        (
            "How long we keep it",
            "Until you stop alerts. If you do not confirm within {days} days, we delete the request.",
        ),
        (
            "Your choices",
            "Every email has a link to stop alerts and delete your data at once. You can also write to {contact}.",
        ),
    ],
    "hi": [
        ("हम कौन हैं", "{business} यह वेबसाइट चलाता है। संपर्क: {contact}।"),
        (
            "हम क्या इकट्ठा करते हैं",
            "आपका ईमेल पता, आपकी चुनी हुई भाषा, वह प्रोजेक्ट जिसके अलर्ट आप चाहते हैं, और आपकी सहमति की तारीख और समय। "
            "हम आपका नाम या फ़ोन नंबर नहीं माँगते।",
        ),
        (
            "क्यों",
            "सिर्फ़ आपके पते की पुष्टि करने और आपके चुने हुए प्रोजेक्ट के अलर्ट ईमेल करने के लिए। "
            "हम इसे विज्ञापन के लिए इस्तेमाल नहीं करते और बेचते नहीं हैं।",
        ),
        (
            "प्रोजेक्ट की जानकारी कहाँ से आती है",
            "हरियाणा RERA की वेबसाइट (haryanarera.gov.in) के सार्वजनिक रिकॉर्ड से। हम वही बताते हैं जो रिकॉर्ड में बिल्डर ने दाखिल किया है। "
            "यह जानकारी है, कानूनी सलाह नहीं, और हमारा HRERA से कोई संबंध नहीं है।",
        ),
        (
            "इसे कौन संभालता है",
            "इस वेबसाइट को चलाने वाली और हमारा ईमेल भेजने वाली कंपनियाँ आपका ईमेल पता हमारी ओर से, सिर्फ़ यह सेवा चलाने के लिए संभालती हैं।",
        ),
        (
            "हम कब तक रखते हैं",
            "जब तक आप अलर्ट बंद नहीं करते। अगर आप {days} दिन में पुष्टि नहीं करते, तो हम अनुरोध मिटा देते हैं।",
        ),
        (
            "आपके विकल्प",
            "हर ईमेल में अलर्ट रोकने और आपका डेटा तुरंत मिटाने का लिंक है। आप {contact} पर भी लिख सकते हैं।",
        ),
    ],
}


def _lang(lang: str) -> str:
    return lang if lang in _TEXT else "en"


def tp(lang: str, key: str, **values: object) -> str:
    """Plain text (for emails)."""
    return _TEXT[_lang(lang)][key].format(**{k: str(v) for k, v in values.items()})


def privacy_sections(lang: str, **values: object) -> List[Tuple[str, str]]:
    fields = {k: str(v) for k, v in values.items()}
    return [(heading, body.format(**fields)) for heading, body in _PRIVACY[_lang(lang)]]
