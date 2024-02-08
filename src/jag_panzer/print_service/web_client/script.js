// fuck javascript
window.self = undefined;


// ===================================
//          Utility functions
// ===================================
const tplate_index = function(tplate_selector, idx_dict){
	const tplate = document.querySelector(tplate_selector).content.cloneNode(true);
	const indexed = {
		'root': tplate.firstElementChild,
	}
	for (const sel_name in idx_dict){
		indexed[sel_name] = tplate.querySelector(idx_dict[sel_name]);
	}

	return indexed
}



// ===================================
//             Constants
// ===================================

const print_columns = [];
const print_groups = {};
let print_groups_idx = [];

const main_dom = document.querySelector('main');
const body_dom = document.querySelector('body');

const empty_special_id = '0'.repeat(32);

const max_groups_per_col = 16;




// ===================================
//              Classes
// ===================================

class PrintGroup {
	constructor(col_idx, group_id){
		this.col_idx = col_idx;
		this.group_id = group_id;
		this.maxlines = 8192;

		this.parent_column = print_columns[col_idx];
		
		print_groups[this.group_id] = this;

		this.dom_data = tplate_index(
			'#print_group_template',
			{
				'header': '.print_group_header',
				'dump':   '.print_group_data',
			}
		);

		this.parent_column.dom_data.groups.append(
			this.dom_data.root
		)
	}

	gprint(text){
		// todo: duplicated code

		const row_dom = tplate_index(
			'#print_row',
			{
				'row': '.print_row',
			}
		)

		if (this.dom_data.dump.children.length > this.maxlines){
			this.dom_data.dump.firstChild.remove();
		}

		row_dom.row.innerText = text;
		this.dom_data.dump.append(row_dom.root);

		if (this.parent_column.s_lock){
			this.dom_data.dump.scrollTo(0, this.dom_data.dump.scrollHeight);
			this.parent_column.dom_data.groups.scrollTo(
				0,
				this.parent_column.dom_data.groups.scrollHeight
			);
		}
	}

	close(){
		delete print_groups[this.group_id];
		this.dom_data.root.remove();
	}
}


class PrintColumn {
	constructor(col_idx, col_header, maxlines=8192) {
		this.col_idx = col_idx;
		this.col_header = col_header;
		this.maxlines = maxlines;
		this.s_lock = true;

		this.dom_data = tplate_index(
			'#worker_template',
			{
				'header':  'header',
				'groups':  '.worker_groups',
				'dump':    '.worker_connections',
				's_lock':  'input',
			}
		)

		this.dom_data.header.innerText = col_header;

		main_dom.append(this.dom_data.root);

		const self = this;
		this.dom_data.s_lock.onchange = function(){
			self.s_lock = self.dom_data.s_lock.checked;
		}
	}

	update(text){
		const row_dom = tplate_index(
			'#print_row',
			{
				'row': '.print_row',
			}
		)

		if (this.dom_data.dump.children.length > this.maxlines){
			this.dom_data.dump.firstChild.remove();
		}

		row_dom.row.innerText = text;
		this.dom_data.dump.append(row_dom.root);

		if (this.s_lock){
			this.dom_data.dump.scrollTo(0, this.dom_data.dump.scrollHeight);
		}
	}
}





// ===================================
//           Work functions
// ===================================


// When a WSS connection to the print server is established -
// the server sends init info, such as the amount of print columns
const process_init_info = function(sv_msg){
	console.group('Processing init info');

	for (const col_idx in sv_msg.val){
		console.log('Creating a print column', col_idx);

		print_columns.push(
			new PrintColumn(
				col_idx,
				sv_msg.val[col_idx]
			)
		)
	}

	console.groupEnd('Processing init info');
}

// Initializing print groups
const create_print_group = function(sv_msg){
	const special_id = sv_msg.val.special_id;
	console.log(
		'Creating a group with the special id of',
		special_id
	)

	if (print_groups[special_id]){
		console.log(
			'Did not create a print group, because',
			special_id,
			'already exists'
		)
		return
	}

	new PrintGroup(sv_msg.val.col_idx, special_id)
	print_groups_idx.unshift(special_id)

	if (print_groups_idx.length > max_groups_per_col){
		const del_id = print_groups_idx.at(-1);

		print_groups[del_id].close();
		delete print_groups[del_id];

		print_groups_idx = print_groups_idx.slice(0, max_groups_per_col);
	}

}

// Deleting print groups
const delete_print_group = function(sv_msg){
	const special_id = sv_msg.val.special_id;
	// console.log('Deleting a print group', special_id)

	// print_groups[special_id].close();
}

// Actually printing text
const print_text = function(sv_msg){
	const special_id = sv_msg.val.special_id;

	if (special_id && special_id != empty_special_id){
		create_print_group(sv_msg)
		print_groups[special_id].gprint(sv_msg.val.data)
		return
	}

	print_columns[sv_msg.val.col_idx].update(sv_msg.val.data)
}


const disconnect_wss = function(){
	wss_con.close();
}



// ===================================
//                 WSS
// ===================================


const wss_cmd_index = {
	'init_info':   process_init_info,
	'print':       print_text,
	'open_group':  create_print_group,
	'close_group': delete_print_group,
}


const wss_con = new WebSocket(
	document.querySelector('body').getAttribute('wss_url')
);

wss_con.addEventListener('open', (event) => {
	wss_con.send('Fuck you server');
	console.log('Opened websocket');
});


wss_con.addEventListener('message', async function(event){
	const msg = JSON.parse(await event.data.text());
	console.log('recv msg:', msg);

	wss_cmd_index[msg.cmd](msg);
});




