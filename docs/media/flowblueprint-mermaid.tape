# Record with: vhs docs/media/flowblueprint-mermaid.tape (from the repository root)
Output docs/media/flowblueprint-mermaid.gif
Set FontSize 18
Set Width 1100
Set Height 620
Set Padding 20
Set TypingSpeed 45ms
Set Shell bash

Hide
Type "rm -f /tmp/FLOW.md && clear"
Enter
Show
Type "flowblueprint tests/examples/station_report.py --level summary -o /tmp/FLOW.md"
Enter
Sleep 3s
Type "head -25 /tmp/FLOW.md"
Enter
Sleep 4s
Type "flowblueprint tests/examples -o /tmp/ARCHITECTURE.md --force"
Enter
Sleep 3s
