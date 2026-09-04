import MasterDataCRUD from './MasterDataCRUD';

export default function RahazaSizesModule({ token }) {
  return (
    <MasterDataCRUD
      title="Ukuran (Size)"
      description="Master ukuran produk. Urutan (order_seq) menentukan tampilan di form & laporan."
      endpoint="/api/rahaza/sizes"
      token={token}
      testIdPrefix="rahaza-size"
      ieKey="sizes"
      columns={[
        { key: 'code', label: 'Kode' },
        { key: 'name', label: 'Nama' },
        { key: 'order_seq', label: 'Urutan' },
      ]}
      fields={[
        { key: 'code', label: 'Kode', required: true, placeholder: 'Contoh: XS / M / XXL' },
        { key: 'name', label: 'Nama', placeholder: 'Opsional, default = Kode' },
        { key: 'order_seq', label: 'Urutan', type: 'number', placeholder: 'Contoh: 1 untuk S, 2 untuk M, dst' },
      ]}
      defaultItem={{ code: '', name: '', order_seq: 0 }}
    />
  );
}
