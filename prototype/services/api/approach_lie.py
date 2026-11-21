"""Ball-specific contact reports used to qualify an approach from rough or sand."""
import re

from shot_evidence import haversine

CHOICES = {
    '长草': ['浅草、能干净触球', '球埋得深', '不清楚'],
    '沙坑': ['能稳定打够、坑沿不挡', '球埋深或坑沿高', '不清楚'],
}


def answer(text, lie):
    clean = re.sub(r'[，,。！!？?\s]', '', text)
    if clean in ('不清楚','不知道','跳过','暂不确定'):
        return 'unknown'
    if lie == '长草':
        if re.search(r'埋.*深|深草|草很深|草很长|草包住', clean):
            return 'blocked'
        if re.search(r'浅草|草不深|球浮|干净触球|正常触球', clean):
            return 'clear'
    if lie == '沙坑':
        if re.search(r'埋.*深|坑沿高|高坑沿|荷包蛋', clean):
            return 'blocked'
        if re.search(r'能稳定打够|能打够|坑沿不挡', clean):
            return 'clear'
    return None


def live_report(consultation, position, now):
    report = consultation.get('lie_playability')
    if not report:
        return None
    if (not position or report['lie'] != consultation.get('lie_report')
            or not 0 <= now-report['at'] <= 600
            or haversine(position['value'], report['point']) > 5):
        consultation.pop('lie_playability', None)
        return None
    return report['status']
