(function () {
  var LAZY_DEFS = {
    'wagtail.blocks.StructBlock': function (inst) { return inst.childBlockDefs; },
    'wagtail.blocks.StreamBlock': function (inst) {
      var defs = [];
      inst.groupedChildBlockDefs.forEach(function (pair) { defs = defs.concat(pair[1]); });
      return defs;
    },
  };

  function patchLazyChildBlockDefsByName(proto, getChildDefs) {
    Object.defineProperty(proto, 'childBlockDefsByName', {
      configurable: true,
      get: function () {
        if (this.childBlockDefsByNameCache === undefined) {
          var map = {};
          getChildDefs(this).forEach(function (def) { map[def.name] = def; });
          this.childBlockDefsByNameCache = map;
        }
        return this.childBlockDefsByNameCache;
      },
      set: function () {},
    });
  }

  function patchTelepath(tp) {
    if (tp.__cyclicUnpackPatched) return;
    tp.__cyclicUnpackPatched = true;

    tp.scanForIds = function (objData, index) {
      if (objData === null || typeof objData !== 'object') return;
      if (Array.isArray(objData)) { objData.forEach((item) => this.scanForIds(item, index)); return; }
      var hasReserved = false;
      if ('_id' in objData) { hasReserved = true; index[objData['_id']] = objData; }
      if ('_type' in objData || '_val' in objData || '_ref' in objData) hasReserved = true;
      if ('_list' in objData) { hasReserved = true; objData['_list'].forEach((item) => this.scanForIds(item, index)); }
      if ('_args' in objData) { hasReserved = true; objData['_args'].forEach((item) => this.scanForIds(item, index)); }
      if ('_dict' in objData) { hasReserved = true; for (var k in objData['_dict']) this.scanForIds(objData['_dict'][k], index); }
      if (!hasReserved) { for (var k in objData) this.scanForIds(objData[k], index); }
    };

    tp.unpackWithRefs = function (objData, index, values) {
      if (objData === null || typeof objData !== 'object') return objData;
      if (Array.isArray(objData)) return objData.map((item) => this.unpackWithRefs(item, index, values));
      var result;
      if ('_ref' in objData) {
        result = objData['_ref'] in values
          ? values[objData['_ref']]
          : this.unpackWithRefs(index[objData['_ref']], index, values);
      } else if ('_val' in objData) {
        result = objData['_val'];
      } else if ('_list' in objData) {
        result = [];
        if ('_id' in objData) values[objData['_id']] = result;
        objData['_list'].forEach((item) => result.push(this.unpackWithRefs(item, index, values)));
      } else if ('_dict' in objData) {
        result = {};
        if ('_id' in objData) values[objData['_id']] = result;
        for (var k in objData['_dict']) result[k] = this.unpackWithRefs(objData['_dict'][k], index, values);
      } else if ('_type' in objData) {
        var ctor = this.constructors[objData['_type']];
        if (typeof ctor !== 'function') throw new Error('telepath encountered unknown object type ' + objData['_type']);
        if ('_id' in objData) {
          var placeholder = Object.create(ctor.prototype);
          values[objData['_id']] = placeholder;
          Object.assign(placeholder, new ctor(...objData['_args'].map((a) => this.unpackWithRefs(a, index, values))));
          return placeholder;
        }
        result = new ctor(...objData['_args'].map((a) => this.unpackWithRefs(a, index, values)));
      } else if ('_id' in objData) {
        throw new Error('telepath encountered object with _id but no type specified');
      } else {
        result = {};
        for (var k in objData) result[k] = this.unpackWithRefs(objData[k], index, values);
        return result;
      }
      if ('_id' in objData) values[objData['_id']] = result;
      return result;
    };

    tp.unpack = function (objData) {
      var index = {};
      this.scanForIds(objData, index);
      return this.unpackWithRefs(objData, index, {});
    };

    // Patch constructors already registered.
    Object.keys(LAZY_DEFS).forEach(function (name) {
      if (tp.constructors[name]) patchLazyChildBlockDefsByName(tp.constructors[name].prototype, LAZY_DEFS[name]);
    });

    // Intercept future registrations.
    var origRegister = tp.register;
    tp.register = function (name, ctor) {
      origRegister.call(this, name, ctor);
      if (name in LAZY_DEFS) patchLazyChildBlockDefsByName(ctor.prototype, LAZY_DEFS[name]);
    };
  }

  if (window.telepath) {
    patchTelepath(window.telepath);
  } else {
    Object.defineProperty(window, 'telepath', {
      configurable: true,
      set: function (tp) {
        Object.defineProperty(window, 'telepath', { configurable: true, writable: true, value: tp });
        patchTelepath(tp);
      },
    });
  }
})();
