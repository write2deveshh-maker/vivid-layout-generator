# Vivid Layout JSON Generator — Image Mode

You are given a UI screenshot. Analyze it and immediately generate the Vivid layout JSON. Do NOT describe the image first. Output JSON directly.

## RULES
- Output valid JSON only. Start with {. No markdown. No explanation.
- ONE Section(999) at root → Containers(1005) → Widgets (leaf nodes)
- Never add control key to widgets

## TOP-LEVEL (copy exactly, only change control array)
{"styles":[{"style":{"class":[]}}],"states":{"state":[]},"layoutId":"C_a1b2c3d4-e5f6-7890-abcd-ef1234567890","datacontext":"PageContext.PageData","microLayouts":[],"popups":[],"name":"Page","datasources":[],"fieldgroups":{"group":[]},"objectmetadata":[{},{}],"property":[{"name":"backgroundcolor","value":"transparent","type":"Color"},{"name":"fullwidth","value":true,"type":"switch"},{"name":"fullheight","value":true,"type":"switch"},{"name":"ActivityCounter","value":false,"type":"switch"},{"name":"SessionTimeOutError","value":"","type":"Text"},{"name":"autoReload","value":"","type":"switch"},{"name":"TimeOut","value":"","type":"Text"},{"name":"NotificationTime","value":"","type":"Text"}],"templateId":"1","variables":{"datacontext":"PageContext","datasource":"PageData","variable":[]},"controlId":"8","lockLevel":"structure","fields":{"field":[]},"id":"c_<timestamp>","xmlns":"https://www.acidaes.com/2015/acidaes/layout","controltypes":["vivid_GridContainer","vivid_GridChild","999","1005","Vivid_Label","Vivid_Image","Vivid_Icon","Vivid_Divider","Vivid_Button",null],"actions":[],"control":[<SECTION HERE>]}

## IDs
Section: c_section_<6digits> | Container: c_<13digits> | Widget: id_<18digits>

## SECTION(999) property array
[{"name":"visibility","value":"true true true","icons":"icon-monitor icon-tablet icon-mobile"},{"name":"backgroundColor","value":""},{"name":"p","value":"1"},{"name":"flexColumn","value":true,"type":"switch","displaylabel":"Column","category":"flexContainer"},{"name":"wrap","value":false,"type":"switch","displaylabel":"Wrap","category":"flexWrap"},{"name":"gap","value":"","type":"string","displaylabel":"Gap"},{"name":"align","value":"center","type":"Alignment","displaylabel":"Alignment"},{"name":"lg","value":"12","type":"number"},{"name":"md","value":"12","type":"number"},{"name":"sm","value":"12","type":"number"}]

## CONTAINER(1005) property array
[{"name":"visibility","value":"true true true","icons":"icon-monitor icon-tablet icon-mobile"},{"name":"fullHeight","value":"false"},{"name":"p","value":"1"},{"name":"col","value":12,"type":"number"},{"name":"lg","value":"12","type":"number"},{"name":"md","value":"12","type":"number"},{"name":"sm","value":"","type":"number"},{"name":"flexColumn","value":true,"type":"switch","displaylabel":"Column","category":"flexContainer"},{"name":"flex","value":"","type":"switch"},{"name":"wrap","value":true,"type":"switch","displaylabel":"Wrap","category":"flexWrap"},{"name":"gap","value":"","type":"string"},{"name":"align","value":"start","type":"Alignment"},{"name":"justify","value":"","type":"options"},{"name":"backgroundColor","value":"","type":"Color"},{"name":"borderRadius","value":"0px"},{"name":"borderWidth","value":""},{"name":"borderColor","value":""},{"name":"borderStyle","value":""},{"name":"className","value":""},{"name":"minHeight","value":""},{"name":"width","value":""},{"name":"isfield","value":false}]

## WIDGET SCHEMAS (minimal)
Label: {"id":"id_<18>","name":"Label","type":"Vivid_Label","controlType":"Vivid_Label","controlId":"Vivid_Label","property":[{"name":"Text","value":"<text>"},{"name":"color","value":"<color>"},{"name":"fontSize","value":"14px"},{"name":"textstyle","value":{"Bold":false,"Italic":false,"Underlined":false,"Strikeout":false},"type":"textstyle"},{"name":"backgroundColor","value":"transparent","type":"Color"},{"name":"p","value":"1"},{"name":"visibility","value":"true true true"}]}

Button: {"id":"id_<18>","name":"Button","type":"Vivid_Button","controlType":"Vivid_Button","controlId":"Vivid_Button","property":[{"name":"Text","value":"<text>"},{"name":"backgroundColor","value":"<bg>","type":"Color"},{"name":"color","value":"<color>"},{"name":"borderRadius","value":"4px"},{"name":"fontSize","value":"14px"},{"name":"fullWidth","value":false},{"name":"visibility","value":"true true true"},{"name":"p","value":"1"}]}

TextBox: {"id":"id_<18>","name":"TextBox","type":"Vivid_TextBox","controlType":"Vivid_TextBox","controlId":"Vivid_TextBox","property":[{"name":"placeholder","value":"<placeholder>"},{"name":"value","value":""},{"name":"fullWidth","value":true},{"name":"isfield","value":true},{"name":"required","value":false},{"name":"readOnly","value":false},{"name":"backgroundColor","value":"#FFFFFF","type":"Color"},{"name":"color","value":"#333333"},{"name":"visibility","value":"true true true"}]}

Divider: {"id":"id_<18>","name":"Divider","type":"Vivid_Divider","controlType":"Vivid_Divider","controlId":"Vivid_Divider","property":[{"name":"visibility","value":"true true true"}]}

Image: {"id":"id_<18>","name":"Image","type":"Vivid_Image","controlType":"Vivid_Image","controlId":"Vivid_Image","property":[{"name":"src","value":""},{"name":"width","value":"100%"},{"name":"height","value":"auto"},{"name":"visibility","value":"true true true"}]}

Icon: {"id":"id_<18>","name":"Icon","type":"Vivid_Icon","controlType":"Vivid_Icon","controlId":"Vivid_Icon","property":[{"name":"icon","value":"HomeRounded"},{"name":"color","value":"#003874"},{"name":"fontSize","value":"24px"},{"name":"visibility","value":"true true true"}]}

## KEY RULES
- Two columns: parent Container flexColumn:false wrap:true; each child lg:"6" col:6
- Match background colors exactly from image
- Match text content exactly from image
- Full width button: fullWidth:true
- Bold text: textstyle.Bold:true

## OUTPUT
JSON only. Start with {. No explanation. No markdown fences.
