# Downlink Desk Operator's Manual

**Read it: [archer7778.github.io/downlink-desk-manual](https://archer7778.github.io/downlink-desk-manual/)** (also as a PDF from that page)

An operator's manual for [Downlink Desk](https://github.com/archer7778/downlink-desk), a ground-segment console that watches real satellites through the SatNOGS network. It is written as structured documentation, following the principles of S1000D, the international specification for technical publications used in defence and aerospace: the content lives in XML data modules, each with its own code, type, issue and date, and is assembled by a publication module into a website and a printable PDF.

## What's in it

| Part | Data modules |
|---|---|
| Front matter | Introduction · Warnings and cautions · Abbreviations and terms |
| Description | System description (with a data-flow figure) · Alert system |
| Operating procedures | Start a shift and complete the daily check · Respond to an alert · Set or change channel limits · Hand over the console · Verify the audit trail |
| Fault isolation | No frames, or satellite may have gone silent · Server cannot collect data from SatNOGS · Console does not open |

Procedures carry preliminary requirements (conditions, time, safety), numbered steps and close-out conditions. Fault isolation modules are yes/no decision trees that end in a result with an action. Warnings, cautions and notes follow the conventional hierarchy.

## How it's built

```
source/
  publication.xml          the publication module: order and grouping of data modules
  DMC-*.xml                one file per data module
  graphics/                figures (SVG)
tools/
  build.py                 checks the source, then writes site/ (standard library only)
  manual.css               screen and print styles
.github/workflows/publish.yml   builds, prints the PDF and publishes to GitHub Pages on every push
```

`python3 tools/build.py` refuses to build if anything is wrong: an element outside the profile, a data module code that doesn't match its file name, a reference to a module that doesn't exist, a figure without alt text, or a fault-isolation answer that leads nowhere or a result that can never be reached. Pull requests run the same checks.

## About the S1000D approach

Data module codes follow the S1000D pattern (model identifier, system and sub-system, disassembly code, information code). Element names such as `levelledPara`, `proceduralStep`, `preliminaryRqmts` and `isolationStep` follow S1000D's, in a simplified profile. The XML is **not** validated against the official S1000D schemas, and the information codes (018 introduction, 012 warnings and cautions, 005 abbreviations, 040 description, 130 operating procedure, 420 fault isolation) are this manual's own, chosen to resemble S1000D usage. It demonstrates the method, not certified compliance.

## How it was made

I specified the manual's scope, structure and conventions. Claude (Anthropic) drafted the data modules and the build pipeline from the Downlink Desk source code, and every procedure was checked against that code for screen labels, defaults and commands. Commits made with Claude are marked as co-authored.

## Licence

Text and figures: CC BY 4.0. Build scripts: MIT.
