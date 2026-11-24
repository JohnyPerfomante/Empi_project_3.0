import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { date } from '../lib/format'
import type { AnswerAccuracyDay } from '../lib/types'
import { Empty, Panel, Table } from './ui'

const percent = (value: number) => `${value.toLocaleString('uk-UA', { maximumFractionDigits: 1 })}%`

export function AnswerAccuracyChart({ days }: { days: AnswerAccuracyDay[] | undefined }) {
  const reviewedDays = days?.filter(day => day.reviewed > 0) ?? []
  const reviewed = reviewedDays.reduce((sum, day) => sum + day.reviewed, 0)
  const correct = reviewedDays.reduce((sum, day) => sum + day.correct, 0)
  return <Panel title="Точність відповідей студентів"
    subtitle="Частка правильних відповідей за останні 30 днів вибраного періоду">
    <div className="panel-body">
    {days && (reviewed ? <>
      <div className="accuracy-summary">
        <strong>{percent(100 * correct / reviewed)}</strong>
        <span>Правильних: {correct} із {reviewed} перевірених відповідей за період графіка</span>
      </div>
      <div className="chart accuracy-chart" role="img" aria-label="Стовпчиковий графік частки правильних відповідей за днями, від 0 до 100 відсотків">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={days} margin={{ left: -12, right: 18, top: 12, bottom: 4 }}>
            <CartesianGrid vertical={false} stroke="#e9eef3" strokeDasharray="4 4"/>
            <XAxis dataKey="date" tickFormatter={value => value.slice(5).split('-').reverse().join('.')}
              tickLine={false} axisLine={false} minTickGap={32} tick={{ fontSize: 11, fill: '#607487' }}/>
            <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={value => `${value}%`}
              tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: '#607487' }}/>
            <Tooltip cursor={{ fill: '#eaf2f2' }} content={({ active, payload }) => {
              const day = payload?.[0]?.payload as AnswerAccuracyDay | undefined
              return active && day && day.accuracy !== null ? <div className="accuracy-tooltip">
                <strong>{date(day.date)}</strong>
                <b>{percent(day.accuracy)} правильних</b>
                <span>Правильні: {day.correct}</span>
                <span>Частково правильні: {day.partial}</span>
                <span>Неправильні: {day.incorrect}</span>
                <span>Усього перевірено: {day.reviewed}</span>
              </div> : null
            }}/>
            <Bar dataKey="accuracy" isAnimationActive={false} fill="#278782" radius={[4, 4, 0, 0]}
              maxBarSize={24} minPointSize={value => value === 0 ? 2 : 0}/>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="accuracy-data">
        <summary>Дані графіка</summary>
        <Table headings={['Дата відповіді', 'Правильні', 'Частково', 'Неправильні', 'Точність']}>
          {reviewedDays.map(day => <tr key={day.date}><td>{date(day.date)}</td><td>{day.correct}</td>
            <td>{day.partial}</td><td>{day.incorrect}</td><td>{percent(day.accuracy!)}</td></tr>)}
        </Table>
      </details>
    </> : <Empty text="У цьому періоді ще немає перевірених відповідей. Графік з’явиться після рішення викладача."/>)}
    <p className="accuracy-note">Точність = правильні / усі перевірені × 100%. Використано останнє рішення викладача
      щодо кожної відповіді та дату її надсилання. Частково правильні входять до перевірених, але не до правильних.
      Неперевірені відповіді й дні без оцінок не враховуються.</p>
    </div>
  </Panel>
}
