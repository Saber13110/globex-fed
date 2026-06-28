import { unpackMessageText } from './message-attachment.util';

describe('unpackMessageText', () => {
  it('returns plain text unchanged', () => {
    const result = unpackMessageText('bonjour');
    expect(result).toEqual({ text: 'bonjour' });
  });

  it('extracts image attachment with data url', () => {
    const raw =
      '[[GLOBEX_ATTACHMENT:{"mime":"image/png","b64":"abc123","name":"scan.png","kind":"image"}]]\nRésume';
    const result = unpackMessageText(raw);
    expect(result.text).toBe('Résume');
    expect(result.fileName).toBe('scan.png');
    expect(result.imageUrl).toBe('data:image/png;base64,abc123');
    expect(result.isDocument).toBeFalsy();
  });

  it('extracts document attachment without image url', () => {
    const raw =
      '[[GLOBEX_ATTACHMENT:{"mime":"application/pdf","b64":"pdfdata","name":"facture.pdf","kind":"document"}]]\nRésume';
    const result = unpackMessageText(raw);
    expect(result.text).toBe('Résume');
    expect(result.fileName).toBe('facture.pdf');
    expect(result.isDocument).toBe(true);
    expect(result.imageUrl).toBeUndefined();
  });
});
