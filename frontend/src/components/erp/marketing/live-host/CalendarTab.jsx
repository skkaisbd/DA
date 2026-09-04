import { Calendar } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

export default function CalendarTab() {
  return (
    <Card>
      <CardContent className="flex flex-col items-center justify-center py-16 gap-3">
        <Calendar size={48} className="text-muted-foreground opacity-40" />
        <p className="font-medium">Calendar View - Coming Soon</p>
        <p className="text-sm text-muted-foreground text-center max-w-md">
          Weekly/monthly calendar view untuk visualisasi shift akan diimplementasi di iterasi berikutnya
        </p>
      </CardContent>
    </Card>
  );
}
