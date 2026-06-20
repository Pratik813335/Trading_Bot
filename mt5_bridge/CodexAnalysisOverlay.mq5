#property strict
#property indicator_chart_window

input string CsvFileName = "codex_analysis\\mt5_objects.csv";
input int RefreshSeconds = 3;

string PREFIX = "Codex_";

color ParseHexColor(string hex)
{
   string value = StringTrimLeft(StringTrimRight(hex));
   if(StringLen(value) == 7 && StringGetCharacter(value, 0) == '#')
   {
      string rr = StringSubstr(value, 1, 2);
      string gg = StringSubstr(value, 3, 2);
      string bb = StringSubstr(value, 5, 2);
      int r = (int)StringToInteger("0x" + rr);
      int g = (int)StringToInteger("0x" + gg);
      int b = (int)StringToInteger("0x" + bb);
      return (color)RGB(r, g, b);
   }
   return clrWhite;
}

datetime ParseTimeValue(string text)
{
   string value = StringTrimLeft(StringTrimRight(text));
   if(value == "")
      return TimeCurrent();
   return StringToTime(value);
}

void ClearCodexObjects()
{
   for(int i = ObjectsTotal(0) - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i);
      if(StringFind(name, PREFIX) == 0)
         ObjectDelete(0, name);
   }
}

void DrawHLine(string name, double price, color lineColor, string labelText)
{
   if(ObjectCreate(0, name, OBJ_HLINE, 0, 0, price))
   {
      ObjectSetInteger(0, name, OBJPROP_COLOR, lineColor);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
      ObjectSetString(0, name, OBJPROP_TEXT, labelText);
   }
}

void DrawRect(string name, datetime t1, double p1, datetime t2, double p2, color fillColor, string labelText)
{
   if(ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2))
   {
      ObjectSetInteger(0, name, OBJPROP_COLOR, fillColor);
      ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, name, OBJPROP_FILL, true);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetString(0, name, OBJPROP_TEXT, labelText);
   }
}

void DrawTextLabel(string name, datetime t1, double p1, color textColor, string labelText)
{
   if(ObjectCreate(0, name, OBJ_TEXT, 0, t1, p1))
   {
      ObjectSetInteger(0, name, OBJPROP_COLOR, textColor);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 10);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial");
      ObjectSetString(0, name, OBJPROP_TEXT, labelText);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
   }
}

void LoadCodexObjects()
{
   int handle = FileOpen(CsvFileName, FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE)
      return;

   ClearCodexObjects();

   bool skipHeader = true;
   while(!FileIsEnding(handle))
   {
      string kind = FileReadString(handle);
      string name = FileReadString(handle);
      string time1 = FileReadString(handle);
      string price1 = FileReadString(handle);
      string time2 = FileReadString(handle);
      string price2 = FileReadString(handle);
      string colorHex = FileReadString(handle);
      string text = FileReadString(handle);

      if(skipHeader)
      {
         skipHeader = false;
         continue;
      }

      string objectName = PREFIX + name;
      color objectColor = ParseHexColor(colorHex);
      double p1 = StringToDouble(price1);
      double p2 = StringToDouble(price2);
      datetime dt1 = ParseTimeValue(time1);
      datetime dt2 = ParseTimeValue(time2);

      if(kind == "hline")
         DrawHLine(objectName, p1, objectColor, text);
      else if(kind == "rect")
         DrawRect(objectName, dt1, p1, dt2, p2, objectColor, text);
      else if(kind == "label")
         DrawTextLabel(objectName, dt1, p1, objectColor, text);
   }

   FileClose(handle);
   ChartRedraw(0);
}

int OnInit()
{
   EventSetTimer(RefreshSeconds);
   LoadCodexObjects();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   LoadCodexObjects();
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   return(rates_total);
}
