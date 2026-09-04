import { useState } from "react";

const encounters = [
  { patient: "PT-20481", title: "Annual wellness visit", status: "draft", created: "9/4/2025, 9:14:22 AM" },
  { patient: "PT-19726", title: "Medication follow-up", status: "processing", created: "9/4/2025, 8:47:06 AM" },
  { patient: "PT-18803", title: "New patient evaluation", status: "completed", created: "9/3/2025, 4:32:18 PM" },
];

export function CurrentPortal() {
  const [created, setCreated] = useState(false);
  return (
    <div className="p-4 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Encounters</h1>
        <button className="text-sm text-blue-600 hover:underline" onClick={() => alert("Signed-in account: Dr. Maya Chen")}>Account</button>
      </div>
      <div className="border rounded p-3 flex gap-2 items-end">
        <div className="flex-1">
          <label className="block text-sm font-medium mb-1">Patient ID / alias</label>
          <input className="w-full border rounded px-2 py-1 text-sm" placeholder="" />
        </div>
        <div className="flex-1">
          <label className="block text-sm font-medium mb-1">Title</label>
          <input className="w-full border rounded px-2 py-1 text-sm" />
        </div>
        <button className="px-3 py-1 text-sm rounded bg-blue-600 text-white" onClick={() => setCreated(true)}>
          {created ? "Created" : "New encounter"}
        </button>
      </div>
      {created && <div className="text-sm text-green-600">Encounter created.</div>}
      <table className="w-full text-sm border-collapse">
        <thead><tr className="border-b bg-gray-50">
          <th className="text-left py-2 px-2">Patient</th><th className="text-left py-2 px-2">Title</th>
          <th className="text-left py-2 px-2">Status</th><th className="text-left py-2 px-2">Created</th>
        </tr></thead>
        <tbody>{encounters.map((e) => <tr key={e.patient} className="border-b hover:bg-gray-50 cursor-pointer" onClick={() => alert(`Opening ${e.patient}`)}>
          <td className="py-2 px-2">{e.patient}</td><td className="py-2 px-2">{e.title}</td>
          <td className="py-2 px-2"><span className="inline-block px-2 py-0.5 rounded text-xs bg-gray-100">{e.status}</span></td>
          <td className="py-2 px-2 text-xs text-gray-600">{e.created}</td>
        </tr>)}</tbody>
      </table>
    </div>
  );
}