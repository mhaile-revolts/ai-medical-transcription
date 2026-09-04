import React from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { colors } from './theme';

export function BrandMark() {
  return <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: colors.teal, alignItems: 'center', justifyContent: 'center' }}>
    <Text style={{ color: '#fff', fontWeight: '800', fontSize: 17 }}>+</Text>
  </View>;
}

export function StatusPill({ children, tone = 'success' }: { children: React.ReactNode; tone?: 'success' | 'warning' }) {
  return <View style={{ alignSelf: 'flex-start', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: tone === 'success' ? colors.mint : colors.warningSurface }}>
    <Text style={{ color: tone === 'success' ? colors.success : colors.warning, fontSize: 11, fontWeight: '700' }}>{children}</Text>
  </View>;
}

export function StepHeader({ number, title, detail, complete }: { number: string; title: string; detail: string; complete?: boolean }) {
  return <View style={{ flexDirection: 'row', alignItems: 'center' }}>
    <View style={{ width: 38, height: 38, borderRadius: 12, backgroundColor: complete ? colors.mintStrong : '#EDF4F1', alignItems: 'center', justifyContent: 'center' }}>
      <Text style={{ color: colors.teal, fontWeight: '800' }}>{complete ? '✓' : number}</Text>
    </View>
    <View style={{ flex: 1, marginLeft: 12 }}>
      <Text style={{ color: colors.ink, fontSize: 14, fontWeight: '800' }}>{title}</Text>
      <Text style={{ color: colors.muted, fontSize: 12, lineHeight: 17, marginTop: 2 }}>{detail}</Text>
    </View>
    {complete && <StatusPill>Complete</StatusPill>}
  </View>;
}

export function SectionCard({ children, highlighted = false }: { children: React.ReactNode; highlighted?: boolean }) {
  return <View style={{ backgroundColor: highlighted ? '#E7F5EF' : colors.surface, borderColor: highlighted ? '#B9DFD2' : colors.line, borderWidth: 1, borderRadius: 17, padding: 17, marginBottom: 13, shadowColor: '#2B6453', shadowOpacity: 0.07, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 2 }}>{children}</View>;
}

export function PrimaryButton({ children, onPress, disabled = false }: { children: React.ReactNode; onPress: () => void; disabled?: boolean }) {
  return <TouchableOpacity accessibilityRole="button" style={{ minHeight: 48, borderRadius: 11, backgroundColor: disabled ? '#C8DAD4' : colors.teal, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16, marginTop: 14 }} onPress={onPress} disabled={disabled}><Text style={{ color: '#fff', fontWeight: '800', fontSize: 13 }}>{children}</Text></TouchableOpacity>;
}