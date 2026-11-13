// Klistra in på https://script.google.com (Nytt projekt), tryck Kör och godkänn behörigheter.
// Länkarna till formuläret och svarskalkylarket skrivs ut i Körningsloggen.
function skapaSecretSanta() {
  const form = FormApp.create('🎅 Secret Santa 2026')
    .setDescription('Fyll i så lottar vi! Du får sedan ett mejl med vem du ska ge en klapp till. Klapparna delas ut på julafton.')
    .setCollectEmail(true)
    .setLimitOneResponsePerUser(false)
    .setAllowResponseEdits(true);

  form.addTextItem().setTitle('Namn').setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Budget?')
    .setChoiceValues(['200 kr', '300 kr', '500 kr', '750 kr'])
    .showOtherOption(true)
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('Önskemål eller tips')
    .setHelpText('Vad gillar du? Saker du önskar dig, intressen, storlekar…');

  form.addParagraphTextItem()
    .setTitle('Något du inte vill ha')
    .setHelpText('T.ex. allergier eller "inga fler ljus"');

  const ss = SpreadsheetApp.create('Secret Santa 2026 – svar');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());

  Logger.log('Dela den här länken: ' + form.getPublishedUrl());
  Logger.log('Redigera formuläret: ' + form.getEditUrl());
  Logger.log('Svaren hamnar här: ' + ss.getUrl());
}
