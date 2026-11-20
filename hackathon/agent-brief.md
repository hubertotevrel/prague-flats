# Brief: where should a personal flat-hunting tool go next?

I built a small tool for my own flat hunt in Prague. I now want to apply to a Czech hackathon on housing for young people, and I want your opinion on how the tool could grow into something useful to many young people, not only me. Several agents are getting this same brief; I will compare the answers, so an honest, specific, opinionated answer is worth more to me than a balanced survey.

If a line starting with `Lens:` appears at the very top of this message, answer from that perspective (the lenses are described at the end). If there is none, answer as a generalist.

## The hackathon

**Domov můj – hackathon o bydlení pro mladé** (domovmujcesko.cz), 15–17 January 2027 at the Míčovna of Prague Castle. Organised by the Office of the President of the Republic with JIC (South Moravian Innovation Centre) and the Institute of Sociology of the Czech Academy of Sciences. The scientific guarantor is the housing sociologist Martin Lux.

- Up to 60 participants aged 18–35, in teams of 4–6, mixing expert insight (economics, sociology, law), communication, design and development, and personal experience of choosing housing.
- The task: design an **independent tool that helps young people understand their housing options and find their way in the housing market**. It can be an app, a website, a calculator or something else. A working product is not required; a considered, verifiable proposal is. The organisers say explicitly that they do not want a finished solution brought in.
- The site stresses that housing takes many forms: city or countryside, flat or house, private rental, municipal flat, co-living, ownership, cooperative.
- Expected outputs: a prototype or demo, work with real data (the example given is a rent versus ownership comparison), a communication plan, a presentation.
- Conditions: independence from banks and developers; real data where data is used; no recommendation of a specific product or provider; room for proposals on what state support is needed.
- The guarantor's three framing facts: (1) housing is one of the least efficient markets and people decide without relevant information; (2) prices move in cycles, and booms and busts are getting longer and larger; (3) prices are driven mainly by demand, so faster permitting alone would not help much.
- Afterwards the jury picks a winning concept, or a combination of elements, which is developed with the co-organisers and piloted.
- The application (deadline 4 December 2026) is about the person or team, not a project submission: a short video (1.5 minutes solo, 2.5 minutes for a team), a motivation text and a skills text of up to 1,000 characters each, and optional portfolio links. Participants receive a data package on 6 January 2027; its contents are not yet known.

## What I built

A scheduled pipeline that ran for six weeks (18 June – 29 July 2026) until I found a flat, then was switched off.

- Several times a day it read the three main Czech rental portals (Sreality, Bezrealitky, iDnes Reality) for Prague.
- It merged the same flat appearing on several portals into one record: 12,140 portal records became 6,960 distinct flats, and 2,592 of those were listed on more than one portal.
- It tracked price over time: 1,031 portal records changed their asking price while being watched.
- It worked out an **all-in monthly cost** (rent plus service charges and utilities). Only one portal publishes charges in a usable form, so 5,154 of the 6,960 all-in figures are estimates, and are flagged as such.
- It computed **door-to-door public transport time** to two workplaces in different districts (mine and my flatmate's) and averaged them.
- It applied hard filters (layouts with a private room each, a ceiling on all-in rent for the whole flat), then gave each surviving flat a 0–1 score: 40% commute, 30% price per m², 30% preferred neighbourhood. 1,196 flats passed the filters and 168 scored high enough to alert.
- It sent a Telegram message within hours of a good flat appearing, with a ready-to-send Czech inquiry text, plus a morning and evening digest and a map of current matches. 142 alerts went out.
- Flats not seen again for four days were treated as gone.

It is about 1,700 lines of Python, a SQLite file, a free scheduler and a static map page, and it cost almost nothing to run.

## What is personal about it, and what I already know is weak

- Every parameter is mine: two specific workplaces, one budget, three preferred neighbourhoods, flat-share layouts, Prague only, private rental only.
- It serves someone who already knows what they want and can afford. It speeds up the hunt; it does not help anyone decide between renting, buying, a cooperative, a municipal flat or staying with their parents, and it says nothing to someone who cannot afford Prague at all.
- It reads the portals without their permission. That was acceptable for one person's private use and is not a foundation for a public tool backed by the President's office.
- Showing people specific listings on specific commercial portals may sit awkwardly with the rule against recommending a provider.
- The data is six weeks of asking rents in one city. It contains no agreed rents, no sale prices, no incomes. How long a flat stayed listed cannot be read off reliably, because one portal was only crawled for its newest listings.
- I believe nothing like it exists in Czechia, but I have not checked properly.

## What I want from you

Work out which parts of this tool carry over to the hackathon's task and which are artefacts of my own search, then tell me where you would take it. The hackathon wants orientation and understanding; my tool does search and speed. I do not know whether the right move is to stretch the tool toward the brief, to keep only one idea from it and build something different around that, or to treat it purely as proof that I can build things and arrive with an open mind. I want your view on that question most of all.

Please answer in English, in under 900 words, using these headings so I can compare answers:

1. **What is worth keeping** — the one or two ideas in the existing tool that would matter to a young person who is not me, and why. Say plainly what should be dropped.
2. **Three directions** — three different ways to develop it, not three sizes of the same idea. For each: who it is for, which decision it helps them make, what data it needs and where that data would come from legitimately, what it reuses from the existing tool, how it sits with the hackathon's conditions, and what a team of five could show after three days.
3. **Your pick** — which one you would pursue and why, and what evidence would change your mind.
4. **The hardest objection** — the strongest criticism a housing researcher or juror would make of your pick, and whether you think it can be answered.
5. **For the application** — the angle you would take in the motivation text and the first ten seconds of the video. An angle, not finished copy.
6. **What you are unsure of** — claims above that rest on your memory of Czech housing data, law, policy or existing tools rather than on something you checked. If you can search the web, check whether comparable Czech tools exist and what public housing data is available (statistical office, ministries, cadastre, price maps, rent indices), and say what you found and where. If you cannot search, say so, and mark guesses as guesses.

A direction that only works for well-paid people in Prague is a weak answer. So is one that amounts to a generic mortgage calculator, a chatbot with no data behind it, or advice that the state should build more flats.

## Lenses

- **Researcher** — a housing sociologist or economist who takes the guarantor's three facts seriously and cares whether the tool changes decisions or only decorates them.
- **Lived experience** — a 23-year-old in a regional town with an irregular income and no family money, for whom ownership looks out of reach.
- **Product** — a product designer who cares about the first minute of use, what the person does next, and why they would return or tell a friend.
- **Data and law** — someone responsible for where the data comes from, whether using it is lawful, what personal data is involved, and who keeps the thing running in two years.
- **Juror** — someone from a public institution who has to defend the winning concept in public: neutrality, political sensitivity, credibility, who could object.
- **Sceptic** — argue that this project should not be the basis of the application at all, as well as you can, then say what would survive that argument.
