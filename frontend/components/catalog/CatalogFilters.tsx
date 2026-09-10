export default function CatalogFilters() {
  return (
    <aside className="w-full md:w-64 flex-shrink-0 space-y-8 pr-4">
      <div>
        <h3 className="text-xs font-bold text-gray-400 tracking-wider mb-4">CATEGORÍAS</h3>
        <ul className="text-sm text-gray-600 space-y-3">
          <li>Sistemas de Ordeño</li>
          <li>Nutrición</li>
          <li>Refacciones</li>
          <li>Confort Animal</li>
          <li>Almacenamiento</li>
        </ul>
      </div>

      <div>
        <h3 className="text-xs font-bold text-gray-400 tracking-wider mb-4">MARCAS</h3>
        <ul className="text-sm text-gray-600 space-y-3">
          <li className="flex items-center justify-between">
            <label className="flex items-center space-x-2">
              <input type="checkbox" defaultChecked className="rounded text-blue-600 border-gray-300 focus:ring-blue-500" />
              <span>GEA</span>
            </label>
            <span className="text-xs text-gray-400 font-medium">(3)</span>
          </li>
          <li className="flex items-center justify-between">
            <label className="flex items-center space-x-2">
              <input type="checkbox" className="rounded text-blue-600 border-gray-300 focus:ring-blue-500" />
              <span>Bionat Sano</span>
            </label>
            <span className="text-xs text-gray-400 font-medium">(3)</span>
          </li>
          <li className="flex items-center justify-between">
            <label className="flex items-center space-x-2">
              <input type="checkbox" className="rounded text-blue-600 border-gray-300 focus:ring-blue-500" />
              <span>Animat</span>
            </label>
            <span className="text-xs text-gray-400 font-medium">(2)</span>
          </li>
          <li className="flex items-center justify-between">
            <label className="flex items-center space-x-2">
              <input type="checkbox" className="rounded text-blue-600 border-gray-300 focus:ring-blue-500" />
              <span>VES-Artex</span>
            </label>
            <span className="text-xs text-gray-400 font-medium">(2)</span>
          </li>
        </ul>
      </div>

      <div>
        <h3 className="text-xs font-bold text-gray-400 tracking-wider mb-4">DISPONIBILIDAD</h3>
        <div className="flex items-center space-x-3">
          <div className="w-10 h-6 bg-green-500 rounded-full flex items-center p-1 cursor-pointer">
            <div className="bg-white w-4 h-4 rounded-full shadow-md transform translate-x-4"></div>
          </div>
          <span className="text-sm text-gray-600">Solo en stock</span>
        </div>
      </div>

      <div>
        <h3 className="text-xs font-bold text-gray-400 tracking-wider mb-4">RANGO DE PRECIO</h3>
        <div className="flex items-center space-x-2">
          <input
            type="text"
            placeholder="$Min"
            className="w-full px-3 py-1.5 border border-gray-300 rounded text-sm text-gray-700 focus:outline-none focus:border-blue-500"
          />
          <span className="text-gray-400">-</span>
          <input
            type="text"
            placeholder="$Max"
            className="w-full px-3 py-1.5 border border-gray-300 rounded text-sm text-gray-700 focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>
    </aside>
  );
}
